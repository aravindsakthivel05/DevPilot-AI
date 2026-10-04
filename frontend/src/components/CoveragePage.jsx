export default function CoveragePage({
  coverage,
  coverageOffset,
  coverageStatus,
  setCoverageOffset,
  setCoverageStatus,
}) {
  return (
    <section className="coverage-page">
      {!coverage ? (
        <p className="muted-note">Loading indexing coverage…</p>
      ) : !coverage.available ? (
        <div className="coverage-card">
          <h2>Coverage unavailable for this snapshot</h2>
          <p>{coverage.reason}</p>
        </div>
      ) : (
        <>
          <div className="coverage-grid">
            <div className="coverage-card">
              <span>Indexed files</span>
              <b>{coverage.summary.indexed_files}</b>
            </div>
            <div className="coverage-card">
              <span>Skipped files</span>
              <b>{coverage.summary.skipped_files}</b>
            </div>
            <div className="coverage-card">
              <span>Ignored directories</span>
              <b>{coverage.summary.ignored_directories}</b>
            </div>
          </div>
          <div className="coverage-card">
            <h2>What the index contains</h2>
            <p className="muted-note">
              Ignored directories are recorded by directory name; their contents are not scanned.{' '}
              {coverage.summary.entries_capped && 'The path list reached its cap.'}
            </p>
            <p className="coverage-reasons">
              {Object.entries(coverage.summary.reason_counts).map(([reason, count]) => (
                <span key={reason}>
                  {reason.replaceAll('_', ' ')}: {count}
                </span>
              ))}
            </p>
            <div className="coverage-controls">
              <label>
                Show
                <select
                  value={coverageStatus}
                  onChange={(e) => {
                    setCoverageStatus(e.target.value);
                    setCoverageOffset(0);
                  }}
                >
                  <option value="all">All paths</option>
                  <option value="indexed">Indexed</option>
                  <option value="skipped">Skipped</option>
                </select>
              </label>
              <span>{coverage.total} recorded paths</span>
            </div>
            <div className="coverage-table-wrap">
              <table className="coverage-table">
                <thead>
                  <tr>
                    <th>Path</th>
                    <th>Status</th>
                    <th>Reason</th>
                    <th>Size</th>
                  </tr>
                </thead>
                <tbody>
                  {coverage.entries.map((entry) => (
                    <tr key={entry.path}>
                      <td>{entry.path}</td>
                      <td>{entry.status}</td>
                      <td>{entry.reason?.replaceAll('_', ' ') || '—'}</td>
                      <td>{entry.size == null ? '—' : `${entry.size} B`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="coverage-pagination">
              <button
                disabled={coverageOffset === 0}
                onClick={() => setCoverageOffset(Math.max(0, coverageOffset - 100))}
              >
                Previous
              </button>
              <span>
                {coverage.total ? coverageOffset + 1 : 0}–
                {Math.min(coverageOffset + 100, coverage.total)} of {coverage.total}
              </span>
              <button
                disabled={coverageOffset + 100 >= coverage.total}
                onClick={() => setCoverageOffset(coverageOffset + 100)}
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
