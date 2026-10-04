import { useEffect, useState } from 'react';
import { api } from '../api';
import { SourceLink, Json, useWork, Status } from './ResearchUI';
export function GraphPage({ repoId, openFile }) {
  const [seed, setSeed] = useState(''),
    [path, setPath] = useState(''),
    [depth, setDepth] = useState(1),
    [direction, setDirection] = useState('both'),
    [kinds, setKinds] = useState(''),
    [graph, setGraph] = useState(null),
    state = useWork();
  async function load(nextSeed = seed) {
    await state.work(async () => {
      const p = new URLSearchParams({ depth, direction, limit: 200 });
      if (nextSeed) p.set('seed', nextSeed);
      if (path) p.set('path', path);
      if (kinds) p.set('kinds', kinds);
      setGraph(await api(`/repositories/${repoId}/graph/neighborhood?${p}`));
    });
  }
  function center(node) {
    setSeed(node.id);
    setPath('');
    state.work(async () =>
      setGraph(
        await api(
          `/repositories/${repoId}/graph/neighborhood?${new URLSearchParams({
            seed: node.id,
            depth,
            direction,
            limit: 200,
            ...(kinds ? { kinds } : {}),
          })}`,
        ),
      ),
    );
  }
  useEffect(() => {
    setSeed('');
    setPath('');
    setGraph(null);
  }, [repoId]);
  return (
    <div className="research-page">
      <h2>Repository Structural Graph</h2>
      <p>
        Explore established relationships. Select a returned node to center the next bounded
        traversal on it.
      </p>
      <div className="research-controls">
        <label>
          Symbol ID
          <input value={seed} onChange={(e) => setSeed(e.target.value)} />
        </label>
        <label>
          File path
          <input value={path} onChange={(e) => setPath(e.target.value)} />
        </label>
        <label>
          Depth
          <select value={depth} onChange={(e) => setDepth(Number(e.target.value))}>
            {[0, 1, 2, 3].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
        <label>
          Direction
          <select value={direction} onChange={(e) => setDirection(e.target.value)}>
            {['both', 'incoming', 'outgoing'].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
        <label>
          Relationships
          <input
            placeholder="calls,imports,tests"
            value={kinds}
            onChange={(e) => setKinds(e.target.value)}
          />
        </label>
      </div>
      <button className="button primary" disabled={state.busy} onClick={() => load()}>
        Explore graph
      </button>
      <Status {...state} />
      {graph && (
        <>
          <p>
            {graph.nodes.length} nodes · {graph.edges.length} edges{' '}
            {graph.truncated && '· limit reached'}
          </p>
          <div className="relationship-map" aria-label="Directed structural relationships">
            {graph.edges.slice(0, 40).map((edge, index) => {
              const source = graph.nodes.find((node) => node.id === edge.source);
              const target = graph.nodes.find((node) => node.id === edge.target);
              if (!source || !target) return null;
              return (
                <div className="relationship-row" key={index}>
                  <button
                    className="relationship-node"
                    disabled={state.busy}
                    onClick={() => center(source)}
                  >
                    <b>{source.qualified || source.name}</b>
                    <small>{source.kind}</small>
                  </button>
                  <span className="relationship-arrow">
                    <b>{edge.kind} →</b>
                    <small>
                      {edge.confidence}
                      {edge.line ? ` · line ${edge.line}` : ''}
                    </small>
                  </span>
                  <button
                    className="relationship-node"
                    disabled={state.busy}
                    onClick={() => center(target)}
                  >
                    <b>{target.qualified || target.name}</b>
                    <small>{target.kind}</small>
                  </button>
                </div>
              );
            })}
          </div>
          {graph.edges.length > 40 && (
            <p>
              The diagram shows the first 40 relationships. All returned nodes and relationships
              remain available below.
            </p>
          )}
          <div className="research-table">
            <table>
              <thead>
                <tr>
                  <th>Entity</th>
                  <th>Kind</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {graph.nodes.map((n) => (
                  <tr key={n.id}>
                    <td>
                      <button
                        className="source-link"
                        disabled={state.busy}
                        onClick={() => center(n)}
                      >
                        {n.qualified || n.name}
                      </button>
                    </td>
                    <td>{n.kind}</td>
                    <td>
                      {n.path && (
                        <>
                          <SourceLink path={n.path} line={n.start_line} openFile={openFile} />
                          {n.end_line > n.start_line && `–${n.end_line}`}
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <details open>
            <summary>Typed relationships</summary>
            <Json value={graph.edges} />
          </details>
        </>
      )}
    </div>
  );
}
