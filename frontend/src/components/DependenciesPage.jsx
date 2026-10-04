import { ArrowRight, GitFork, Search, Braces } from 'lucide-react';
export default function DependenciesPage({
  activeNode,
  connected,
  graph,
  nodeId,
  query,
  setNodeId,
  setQuery,
}) {
  return (
    <div className="graph-layout">
      <div className="file-list">
        <label className="search-input">
          <Search size={15} />
          <input
            aria-label="Search symbols"
            placeholder="Find a symbol…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        {graph.nodes
          .filter((n) => n.qualified.toLowerCase().includes(query.toLowerCase()))
          .slice(0, 200)
          .map((n) => (
            <button
              className={nodeId === n.id ? 'chosen' : ''}
              key={n.id}
              onClick={() => setNodeId(n.id)}
            >
              <Braces size={14} />
              <span>
                {n.name}
                <small>{n.kind}</small>
              </span>
            </button>
          ))}
      </div>
      <div className="graph-main">
        <div className="code-title">
          Symbol neighbourhood<span>{connected.length} direct relationships</span>
        </div>
        <div className="central-node">
          <GitFork size={22} />
          <div>
            <b>{activeNode?.qualified}</b>
            <small>
              {activeNode?.path}:{activeNode?.start_line}
            </small>
          </div>
        </div>
        <div className="edge-list">
          {connected.length ? (
            connected.map((e, i) => {
              const other = graph.nodes.find(
                (n) => n.id === (e.source === nodeId ? e.target : e.source),
              );
              return (
                <button key={i} onClick={() => setNodeId(other?.id)}>
                  <span className="edge-type">
                    {e.source === nodeId ? 'Outgoing' : 'Incoming'} · {e.kind}
                  </span>
                  <ArrowRight size={16} />
                  <b>{other?.qualified}</b>
                  <span className="kind">{e.confidence}</span>
                </button>
              );
            })
          ) : (
            <p className="muted-note">No resolved edges for this symbol.</p>
          )}
        </div>
        <p className="muted-note">
          Calls with unresolved targets are counted in the snapshot summary and are not drawn as
          confirmed relationships.
        </p>
      </div>
    </div>
  );
}
