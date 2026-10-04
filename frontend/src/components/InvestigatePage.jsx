import AnswerCoverage from './AnswerCoverage';
import {
  ArrowUpRight,
  ArrowUp,
  GitFork,
  Search,
  Layers,
  Plus,
  Check,
  ChevronRight,
  Loader2,
  Clock,
  ShieldCheck,
  Command,
} from 'lucide-react';
export default function InvestigatePage({
  ask,
  busy,
  deep,
  health,
  history,
  indexStatus,
  learningQueuedRun,
  mode,
  openFile,
  question,
  queueAnswerForReview,
  repo,
  result,
  setDeep,
  setMode,
  setQuestion,
  setResult,
  setUseModel,
  suggestions,
  useModel,
}) {
  return (
    <div className="investigate-layout">
      <section>
        <div className="question-card">
          <div className="card-label">
            <span>
              <Search size={16} />
              Ask your codebase
            </span>
            <span className="tiny-tag">
              {health?.model_configured ? 'MODEL CONFIGURED' : 'RETRIEVAL MODE'}
            </span>
          </div>
          <textarea
            aria-label="Repository question"
            placeholder="How does this repository handle a request?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) ask();
            }}
          />
          <div className="question-toolbar">
            <div className="query-options">
              <div className="mode-select">
                <Layers size={14} />
                <select
                  aria-label="Retrieval strategy"
                  value={mode}
                  onChange={(e) => setMode(e.target.value)}
                >
                  <option value="hybrid">Hybrid retrieval</option>
                  <option value="lexical">Text baseline</option>
                  <option value="graph">Graph expansion</option>
                  <option
                    value="semantic"
                    disabled={!health?.embedding_configured || !indexStatus?.semantic_ready}
                  >
                    Semantic retrieval
                  </option>
                </select>
              </div>
              <div className="mode-select">
                <select
                  aria-label="Answer style"
                  value={useModel ? 'ai' : 'evidence'}
                  onChange={(e) => setUseModel(e.target.value === 'ai')}
                >
                  <option value="ai">AI explanation</option>
                  <option value="evidence">Evidence only</option>
                </select>
              </div>
              {health?.langgraph_enabled && (
                <div className="mode-select">
                  <select
                    aria-label="Investigation depth"
                    value={deep ? 'deep' : 'quick'}
                    onChange={(e) => setDeep(e.target.value === 'deep')}
                  >
                    <option value="quick">Quick answer</option>
                    <option value="deep">Deep investigation</option>
                  </select>
                </div>
              )}
            </div>
            <div className="ask-actions">
              <span>⌘ Enter</span>
              <button
                className="ask-button"
                disabled={busy || !question.trim()}
                onClick={() => ask()}
                aria-label="Ask question"
              >
                {busy ? <Loader2 size={18} className="spin" /> : <ArrowUp size={20} />}
              </button>
            </div>
          </div>
        </div>
        {!result && (
          <>
            <div className="section-title">
              START AN INVESTIGATION<span>Suggested questions</span>
            </div>
            <div className="suggestions">
              {(repo.name === 'parcel-service'
                ? suggestions
                : [
                    'What are the main entry points in this repository?',
                    'How are requests validated and errors handled?',
                    'Which tests cover the core functionality?',
                  ]
              ).map((q) => (
                <button key={q} disabled={busy} onClick={() => ask(q)}>
                  <span>{q}</span>
                  <ArrowUpRight size={16} />
                </button>
              ))}
            </div>
            <div className="explain-panel">
              <div className="explain-line">
                <span className="step-dot">1</span>
                <div>
                  <b>Find relevant symbols</b>
                  <p>Search source code and documentation.</p>
                </div>
                <span className="step-dot">2</span>
                <div>
                  <b>Follow dependencies</b>
                  <p>Expand through structural relationships.</p>
                </div>
                <span className="step-dot">3</span>
                <div>
                  <b>Show the evidence</b>
                  <p>Trace every source back to its snapshot.</p>
                </div>
              </div>
            </div>
          </>
        )}
        {result && (
          <div className="result">
            <div className="result-heading">
              <span className="result-icon">
                <Command size={16} />
              </span>
              <b>
                {result.abstained
                  ? 'Cannot determine from snapshot'
                  : result.generated
                    ? result.partial
                      ? 'Partial repository answer'
                      : 'Repository answer'
                    : 'Evidence report'}
              </b>
              <span className="time">
                <Clock size={13} />
                {(result.elapsed_ms / 1000).toFixed(2)}s
              </span>
            </div>
            {result.warning && <div className="warning">{result.warning}</div>}
            <div className="answer-text">
              {result.answer.split(/(\[\d+\])/g).map((part, index) => {
                const match = part.match(/^\[(\d+)\]$/);
                if (!match) return part;
                const number = Number(match[1]);
                const source = result.evidence[number - 1];
                const citation = (result.claims || [])
                  .flatMap((claim) => claim.citations || [])
                  .find((c) => c.source_id === number);
                return source ? (
                  <button
                    className="inline-citation"
                    key={index}
                    onClick={() => openFile(source.path, citation?.start_line || source.start_line)}
                  >
                    {part}
                  </button>
                ) : (
                  part
                );
              })}
            </div>
            <AnswerCoverage aspects={result.aspect_statuses} />
            <div className="result-meta">
              <span>Execution: not run</span>
              {result.workflow && (
                <span>LangGraph · {result.workflow.retrieval_passes} search pass(es)</span>
              )}
              {result.generated && (
                <span>Source identity and lines checked · meaning needs review</span>
              )}
              <span>
                {result.semantic_used ? 'Semantic + structural context' : 'Text-based context'}
              </span>
              {result.usage?.total_tokens && <span>{result.usage.total_tokens} tokens</span>}
              {result.generation_diagnostics?.attempt_count > 0 && (
                <span>
                  Model{' '}
                  {result.generation_diagnostics.provider_calls ??
                    result.generation_diagnostics.attempt_count}{' '}
                  call
                  {(result.generation_diagnostics.provider_calls ??
                    result.generation_diagnostics.attempt_count) === 1
                    ? ''
                    : 's'}{' '}
                  · {(result.generation_diagnostics.total_request_ms / 1000).toFixed(1)}s
                </span>
              )}
            </div>
            {result.id && (
              <button
                className="button learning-queue-button"
                disabled={busy || learningQueuedRun === result.id}
                onClick={queueAnswerForReview}
              >
                {learningQueuedRun === result.id ? <Check size={15} /> : <Plus size={15} />}
                {learningQueuedRun === result.id ? 'Queued for review' : 'Queue for review'}
              </button>
            )}
            {result.citation_check.invalid.length > 0 && (
              <div className="warning">
                Unresolved citations: {result.citation_check.invalid.join(', ')}
              </div>
            )}
            {result.generation_context?.length > 0 && (
              <details className="evidence">
                <summary>Exact excerpts provided to the model</summary>
                {result.generation_context.map((item) => (
                  <div key={item.source_id}>
                    <b>
                      [{item.source_id}] {item.qualified}
                    </b>
                    <small>{item.path}</small>
                    <pre>
                      {item.source
                        .split('\n')
                        .map((line, i) => `${item.source_line_numbers[i]}: ${line}`)
                        .join('\n')}
                    </pre>
                  </div>
                ))}
              </details>
            )}
            <div className="section-title">
              SOURCE EVIDENCE<span>{result.evidence.length} locations</span>
            </div>
            {result.evidence.map((s, i) => (
              <details className="evidence" key={s.id} open={i === 0}>
                <summary>
                  <span className="citation">{i + 1}</span>
                  <div>
                    <b>{s.name}</b>
                    <small>
                      {s.path}:{s.start_line}–{s.end_line}
                    </small>
                  </div>
                  <span className="kind">{s.kind}</span>
                  <ChevronRight size={15} />
                </summary>
                <div className="evidence-reason">
                  <GitFork size={13} />
                  {s.reason}
                  <button onClick={() => openFile(s.path, s.start_line)}>
                    Open file
                    <ArrowUpRight size={13} />
                  </button>
                </div>
                <pre>{s.source}</pre>
                {s.truncated && (
                  <small className="truncate">Excerpt truncated to fit the context budget.</small>
                )}
              </details>
            ))}
          </div>
        )}
      </section>
      <aside className="context-panel">
        <div className="section-title">
          SNAPSHOT CONTEXT
          <Layers size={15} />
        </div>
        <div className="context-row">
          <span>Analysis</span>
          <b>
            {Object.keys(repo.stats.languages || {})
              .filter((language) => language !== 'text')
              .join(', ') || 'Legacy source index'}
          </b>
        </div>
        <div className="context-row">
          <span>Search</span>
          <b>{repo.stats.embedding_status === 'ready' ? 'Embeddings + text' : 'Text + graph'}</b>
        </div>
        <div className="context-row">
          <span>Snapshot</span>
          <code>{repo.fingerprint?.slice(0, 10)}</code>
        </div>
        <div className="context-row">
          <span>Unresolved references</span>
          <b>{repo.stats.unresolved_count || 0}</b>
        </div>
        <p className="muted-note">
          Static relationships are evidence, not a complete model of runtime behaviour.
        </p>
        <div className="panel-divider" />
        <div className="section-title">
          RECENT INVESTIGATIONS
          <Clock size={14} />
        </div>
        {history.length ? (
          history.slice(0, 6).map((h) => (
            <button
              className="history-item"
              key={h.id}
              onClick={() => {
                setQuestion(h.question);
                setResult(h.result);
              }}
            >
              <Search size={13} />
              <span>{h.question}</span>
              <ChevronRight size={13} />
            </button>
          ))
        ) : (
          <p className="muted-note">Your investigations will appear here.</p>
        )}
        <div className="panel-tip">
          <span>BUILT ON EVIDENCE</span>
          <p>
            Source citations show what the answer used. Suggested fixes and tests need manual
            review.
          </p>
          <ShieldCheck size={24} />
        </div>
      </aside>
    </div>
  );
}
