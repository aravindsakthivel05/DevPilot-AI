import { useEffect, useState } from 'react';
import { api } from '../api';
import { DraftView, useWork, Status } from './ResearchUI';
export function SuggestionsPage({ repoId, openFile }) {
  const [request, setRequest] = useState(''),
    [result, setResult] = useState(null),
    [saved, setSaved] = useState([]),
    state = useWork();
  useEffect(() => {
    state.work(async () => setSaved(await api(`/repositories/${repoId}/fix-suggestions`)));
  }, [repoId]);
  async function draft(kind) {
    await state.work(async () => {
      const r = await api(`/repositories/${repoId}/${kind}`, { request });
      setResult(r);
      setSaved(await api(`/repositories/${repoId}/fix-suggestions`));
    });
  }
  return (
    <div className="research-page">
      <h2>Fix and test suggestions</h2>
      <p>
        Describe the expected behavior and the suspected problem. Drafts are for manual review;
        DevPilot does not apply or execute them.
      </p>
      <textarea
        aria-label="Suggestion request"
        rows={5}
        value={request}
        onChange={(e) => setRequest(e.target.value)}
        placeholder="Describe the problem, relevant symbols, and expected behavior…"
      />
      <div className="research-actions">
        <button
          className="button primary"
          disabled={state.busy || !request.trim()}
          onClick={() => draft('fix-suggestions')}
        >
          Draft fix and test
        </button>
        <button
          className="button"
          disabled={state.busy || !request.trim()}
          onClick={() => draft('test-suggestions')}
        >
          Draft test only
        </button>
      </div>
      <Status {...state} />
      {result && <DraftView draft={result} openFile={openFile} />}
      <details>
        <summary>Saved drafts ({saved.length})</summary>
        {saved.map((r) => (
          <button className="research-saved" key={r.id} onClick={() => setResult(r)}>
            {r.summary || r.id}
          </button>
        ))}
      </details>
    </div>
  );
}
