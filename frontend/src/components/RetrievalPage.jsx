import { useState } from 'react';
import { api } from '../api';
import { SourceLink, Json, useWork, Status } from './ResearchUI';
export function RetrievalPage({ repoId, openFile }) {
  const [question, setQuestion] = useState(''),
    [mode, setMode] = useState('hybrid'),
    [hops, setHops] = useState(2),
    [result, setResult] = useState(null),
    state = useWork();
  return (
    <div className="research-page">
      <h2>Retrieval diagnostics</h2>
      <p>
        Inspect candidates, actual component scores, graph expansion, reranking and retrieval timing
        without generating an answer.
      </p>
      <textarea
        aria-label="Retrieval question"
        rows={3}
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
      />
      <div className="research-controls">
        <label>
          Mode
          <select value={mode} onChange={(e) => setMode(e.target.value)}>
            {['lexical', 'semantic', 'graph', 'hybrid'].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
        <label>
          Graph depth
          <select value={hops} onChange={(e) => setHops(Number(e.target.value))}>
            {[0, 1, 2, 3].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
      </div>
      <button
        className="button primary"
        disabled={state.busy || question.trim().length < 2}
        onClick={() =>
          state.work(async () =>
            setResult(
              await api(`/repositories/${repoId}/retrieve`, { question, mode, hops, limit: 10 }),
            ),
          )
        }
      >
        Retrieve evidence
      </button>
      <Status {...state} />
      {result && (
        <>
          <p>{result.warning}</p>
          {result.evidence.map((e) => (
            <article className="research-card" key={e.id}>
              <b>{e.qualified}</b>{' '}
              <SourceLink path={e.path} line={e.start_line} openFile={openFile} />
              <Json
                value={{
                  scores: e.component_scores,
                  reason: e.reason,
                  traversal: e.traversal,
                  retrieval_sources: e.retrieval_sources,
                }}
              />
            </article>
          ))}
          <details open>
            <summary>Full retrieval trace</summary>
            <Json value={result.trace} />
          </details>
        </>
      )}
    </div>
  );
}
