import { useState } from 'react';
export function SourceLink({ path, line, openFile }) {
  return (
    <button className="source-link" onClick={() => openFile(path, line)}>
      {path}
      {line ? `:${line}` : ''}
    </button>
  );
}

export function Json({ value }) {
  return <pre className="research-json">{JSON.stringify(value, null, 2)}</pre>;
}

export function useWork() {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  async function work(action) {
    setBusy(true);
    setError('');
    try {
      await action();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, work };
}

export function Status({ busy, error }) {
  return (
    <>
      {busy && <p role="status">Working…</p>}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </>
  );
}

export function DraftView({ draft, openFile }) {
  return (
    <article className="research-card">
      <h3>Unverified draft</h3>
      <p>{draft.summary}</p>
      <p>No code or tests were executed.</p>
      {draft.patch && (
        <>
          <h4>Suggested patch</h4>
          <pre className="research-json">{draft.patch}</pre>
        </>
      )}
      {Object.entries(draft.extra_tests || {}).map(([path, source]) => (
        <div key={path}>
          <h4>Suggested test: {path}</h4>
          <pre className="research-json">{source}</pre>
        </div>
      ))}
      {draft.suggested_test && <p>{draft.suggested_test}</p>}
      {draft.missing_information?.length > 0 && (
        <p>
          <b>Needs review:</b> {draft.missing_information.join(' ')}
        </p>
      )}
      <details>
        <summary>Source evidence</summary>
        {(draft.evidence || []).map((source, index) =>
          openFile ? (
            <p key={index}>
              <SourceLink
                path={source.path || source.file}
                line={source.start_line}
                openFile={openFile}
              />
              {source.qualified && ` · ${source.qualified}`}
            </p>
          ) : (
            <Json key={index} value={source} />
          ),
        )}
      </details>
    </article>
  );
}
