import { useState } from 'react';
import { api } from '../api';
import { Json, useWork, Status } from './ResearchUI';
export function ResearchEvaluationPage({ repoId }) {
  const [cases, setCases] = useState(
      '[\n  {"question": "Your source-backed question", "expected_ids": ["indexed-symbol-id"]}\n]',
    ),
    [result, setResult] = useState(null),
    state = useWork();
  return (
    <div className="research-page">
      <h2>Retrieval experiments</h2>
      <p>
        Supply reviewed expected symbol IDs from this snapshot. Compares lexical, semantic, graph,
        hybrid and ablations. Missing embeddings are reported as unavailable. These metrics do not
        grade answer correctness.
      </p>
      <textarea
        aria-label="Evaluation cases JSON"
        rows={8}
        value={cases}
        onChange={(e) => setCases(e.target.value)}
      />
      <button
        className="button primary"
        disabled={state.busy}
        onClick={() =>
          state.work(async () =>
            setResult(
              await api(`/repositories/${repoId}/research-evaluate`, { cases: JSON.parse(cases) }),
            ),
          )
        }
      >
        Run comparisons
      </button>
      <Status {...state} />
      {result && (
        <>
          <div className="research-table">
            <table>
              <thead>
                <tr>
                  <th>Variant</th>
                  <th>Available cases</th>
                  <th>Recall@5</th>
                  <th>MRR@5</th>
                  <th>NDCG@5</th>
                  <th>All evidence@5</th>
                  <th>Mean latency</th>
                </tr>
              </thead>
              <tbody>
                {result.results.map(({ variant, cases: rows }) => {
                  const available = rows.filter((row) => row.available);
                  const mean = (field) =>
                    available.length
                      ? (
                          available.reduce((total, row) => total + row.at_5[field], 0) /
                          available.length
                        ).toFixed(3)
                      : 'Unavailable';
                  return (
                    <tr key={variant.name}>
                      <td>{variant.name}</td>
                      <td>
                        {available.length}/{rows.length}
                      </td>
                      <td>{mean('recall')}</td>
                      <td>{mean('mrr')}</td>
                      <td>{mean('ndcg')}</td>
                      <td>
                        {available.filter((row) => row.at_5.all_required_evidence).length}/
                        {available.length}
                      </td>
                      <td>
                        {available.length
                          ? `${(available.reduce((total, row) => total + row.elapsed_ms, 0) / available.length).toFixed(1)} ms`
                          : 'Unavailable'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <details>
            <summary>Full results, warnings and metrics at 5/10</summary>
            <Json value={result} />
          </details>
        </>
      )}
    </div>
  );
}
