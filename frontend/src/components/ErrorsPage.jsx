import { useEffect, useState } from 'react';
import { api } from '../api';
import { SourceLink, Json, useWork, Status, DraftView } from './ResearchUI';
export function ErrorsPage({ repoId, openFile }) {
  const [issues, setIssues] = useState([]),
    [details, setDetails] = useState(null),
    state = useWork();
  useEffect(() => {
    state.work(async () => setIssues((await api(`/repositories/${repoId}/errors`)).issues));
  }, [repoId]);
  return (
    <div className="research-page">
      <h2>Error analysis</h2>
      <p>
        Static candidates with source evidence. A candidate may be intentional; review its
        assumptions before making changes.
      </p>
      <button
        className="button primary"
        disabled={state.busy}
        onClick={() =>
          state.work(async () => {
            const r = await api(`/repositories/${repoId}/errors/analyze`, {});
            setIssues(r.issues);
            setDetails(null);
          })
        }
      >
        Analyze repository
      </button>
      <Status {...state} />
      <p>{issues.length} candidates</p>
      {issues.map((issue) => (
        <article className="research-card" key={issue.id}>
          <h3>
            {issue.type.replaceAll('_', ' ')}{' '}
            <small>
              {issue.severity} · {issue.confidence}
            </small>
          </h3>
          <SourceLink path={issue.file} line={issue.line} openFile={openFile} />
          <p>{issue.message}</p>
          {issue.symbol && (
            <p>
              <b>Owning symbol:</b> {issue.symbol}
            </p>
          )}
          <p>
            <b>Candidate cause:</b> {issue.root_cause}
          </p>
          <p>
            <b>Suggested action:</b> {issue.suggested_fix}
          </p>
          <p>
            <b>Suggested regression check:</b> {issue.suggested_test}
          </p>
          <details>
            <summary>Evidence and related symbols</summary>
            <Json value={{ evidence: issue.evidence, related_symbols: issue.related_symbols }} />
          </details>
          <div className="research-actions">
            <button
              className="button"
              disabled={state.busy}
              onClick={() =>
                state.work(async () =>
                  setDetails(await api(`/repositories/${repoId}/errors/${issue.id}/explain`, {})),
                )
              }
            >
              Investigate cause
            </button>
            <button
              className="button"
              disabled={state.busy}
              onClick={() =>
                state.work(async () =>
                  setDetails(
                    await api(`/repositories/${repoId}/fix-suggestions`, { issue_id: issue.id }),
                  ),
                )
              }
            >
              Draft fix and test
            </button>
            <button
              className="button"
              disabled={state.busy}
              onClick={() =>
                state.work(async () =>
                  setDetails(
                    await api(`/repositories/${repoId}/test-suggestions`, { issue_id: issue.id }),
                  ),
                )
              }
            >
              Draft test only
            </button>
          </div>
        </article>
      ))}
      {details &&
        (details.investigation ? (
          <article className="research-card">
            <h3>Cause investigation</h3>
            <p>{details.issue.root_cause}</p>
            <pre className="research-json">{details.investigation.answer}</pre>
            <p>Static/model reasoning only; the candidate remains unverified.</p>
            {(details.investigation.evidence || []).map((source) => (
              <p key={source.id}>
                <SourceLink path={source.path} line={source.start_line} openFile={openFile} />
              </p>
            ))}
            <details>
              <summary>Statuses and diagnostics</summary>
              <Json
                value={{
                  aspects: details.investigation.aspect_statuses,
                  warning: details.investigation.warning,
                }}
              />
            </details>
          </article>
        ) : (
          <DraftView draft={details} openFile={openFile} />
        ))}
    </div>
  );
}
