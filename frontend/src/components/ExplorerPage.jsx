import { useEffect } from 'react';
import { Search, Code2 } from 'lucide-react';
export default function ExplorerPage({ file, files, openFile, query, relatedTests, setQuery }) {
  useEffect(() => {
    if (file?.focusLine)
      document.getElementById(`source-line-${file.focusLine}`)?.scrollIntoView({ block: 'center' });
  }, [file]);
  return (
    <div className="explorer">
      <div className="file-list">
        <label className="search-input">
          <Search size={15} />
          <input
            aria-label="Search files"
            placeholder="Find a file…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        {files
          .filter((f) => f.path.toLowerCase().includes(query.toLowerCase()))
          .map((f) => (
            <button
              className={file?.path === f.path ? 'chosen' : ''}
              key={f.path}
              onClick={() => openFile(f.path)}
            >
              <Code2 size={14} />
              {f.path}
            </button>
          ))}
      </div>
      <div className="code-view">
        <div className="code-title">
          {file?.path || 'Select a file'}
          <span>{file ? 'Snapshot source' : 'Read-only explorer'}</span>
        </div>
        {file && relatedTests?.links?.length > 0 && (
          <div className="related-tests">
            <b>Related test candidates</b>
            <div>
              {relatedTests.links.slice(0, 6).map((link) => (
                <button key={link.path} onClick={() => openFile(link.path)}>
                  {link.path}
                  <small>{link.confidence === 'static' ? 'Static reference' : 'Name match'}</small>
                </button>
              ))}
            </div>
            <small>{relatedTests.notice}</small>
          </div>
        )}
        {file ? (
          <div className="source-lines">
            {file.content.split('\n').map((l, i) => (
              <div
                key={i}
                id={`source-line-${i + 1}`}
                className={file.focusLine === i + 1 ? 'focused-line' : ''}
              >
                <span>{i + 1}</span>
                <code>{l || ' '}</code>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-pane">
            <Code2 size={36} />
            <p>Browse the code behind your answers.</p>
          </div>
        )}
      </div>
    </div>
  );
}
