import React, { useEffect, useState } from 'react';
import {
  ArrowUpRight,
  ArrowUp,
  ArrowRight,
  GitBranch,
  GitFork,
  Search,
  Layers,
  Terminal,
  BookOpen,
  Plus,
  Check,
  ChevronRight,
  Code2,
  Files,
  Activity,
  Settings2,
  Loader2,
  X,
  ExternalLink,
  RefreshCw,
  Beaker,
  Clock,
  ShieldCheck,
  AlertCircle,
  Braces,
  Command,
} from 'lucide-react';

async function api(path, body) {
  const r = await fetch(
    '/api' + path,
    body === undefined
      ? {}
      : {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        },
  );
  const data = await r.json();
  if (!r.ok)
    throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
  return data;
}
const tabs = [
  ['Investigate', Search],
  ['Code explorer', Files],
  ['Coverage', Layers],
  ['Dependencies', GitFork],
  ['Verification', ShieldCheck],
  ['Evaluation', Beaker],
];
const suggestions = [
  'How is an international shipping quote calculated?',
  'Which functions call calculate_quote?',
  'Where is parcel input validated?',
];

export default function App() {
  const [repos, setRepos] = useState([]),
    [selected, setSelected] = useState(null),
    [tab, setTab] = useState('Investigate');
  const [health, setHealth] = useState(null),
    [error, setError] = useState(''),
    [modal, setModal] = useState(false),
    [source, setSource] = useState('');
  const [question, setQuestion] = useState(''),
    [result, setResult] = useState(null),
    [busy, setBusy] = useState(false),
    [mode, setMode] = useState('hybrid'),
    [useModel, setUseModel] = useState(true),
    [deep, setDeep] = useState(false);
  const [files, setFiles] = useState([]),
    [file, setFile] = useState(null),
    [relatedTests, setRelatedTests] = useState(null),
    [graph, setGraph] = useState({ nodes: [], edges: [] }),
    [history, setHistory] = useState([]);
  const [coverage, setCoverage] = useState(null),
    [coverageStatus, setCoverageStatus] = useState('all'),
    [coverageOffset, setCoverageOffset] = useState(0);
  const [query, setQuery] = useState(''),
    [nodeId, setNodeId] = useState(null),
    [run, setRun] = useState(null),
    [guidedRun, setGuidedRun] = useState(null),
    [target, setTarget] = useState('tests'),
    [image, setImage] = useState('devpilot-runner:local'),
    [runner, setRunner] = useState('python');
  const [patch, setPatch] = useState(''),
    [proposalRequest, setProposalRequest] = useState(''),
    [proposal, setProposal] = useState(null),
    [generatedTests, setGeneratedTests] = useState(null),
    [evalText, setEvalText] = useState(
      JSON.stringify(
        [
          {
            question: suggestions[0],
            expected_symbols: [
              'parcel.api.shipping_quote',
              'parcel.pricing.calculate_quote',
              'parcel.pricing.base_rate',
            ],
          },
        ],
        null,
        2,
      ),
    ),
    [evaluation, setEvaluation] = useState(null);
  const [learningCases, setLearningCases] = useState([]),
    [activeLearningCase, setActiveLearningCase] = useState(null),
    [learningSaved, setLearningSaved] = useState(false),
    [learningQueuedRun, setLearningQueuedRun] = useState(''),
    [learningSplit, setLearningSplit] = useState('development'),
    [learningAnswerable, setLearningAnswerable] = useState(true),
    [learningSymbols, setLearningSymbols] = useState(''),
    [learningAnswer, setLearningAnswer] = useState(''),
    [learningSources, setLearningSources] = useState('[]'),
    [learningNotes, setLearningNotes] = useState(''),
    [learningAnswerCorrect, setLearningAnswerCorrect] = useState(null),
    [learningClaimsSupported, setLearningClaimsSupported] = useState(null),
    [learningAbstention, setLearningAbstention] = useState(null);
  const repo = repos.find((r) => r.id === selected),
    ready = repo?.status === 'ready';
  async function refresh() {
    try {
      const r = await api('/repositories');
      setRepos(r);
      setSelected((s) => s || r[0]?.id || null);
    } catch (e) {
      setError(e.message);
    }
  }
  useEffect(() => {
    refresh();
    api('/health')
      .then(setHealth)
      .catch((e) => setError(e.message));
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    setResult(null);
    setFile(null);
    setRelatedTests(null);
    setRun(null);
    setGuidedRun(null);
    setProposal(null);
    setGeneratedTests(null);
    setEvaluation(null);
    setLearningCases([]);
    setActiveLearningCase(null);
    setLearningSaved(false);
    setLearningQueuedRun('');
    setFiles([]);
    setGraph({ nodes: [], edges: [] });
    setNodeId(null);
    setHistory([]);
    setCoverage(null);
    setCoverageStatus('all');
    setCoverageOffset(0);
    setQuery('');
    setError('');
  }, [selected]);
  useEffect(() => {
    if (!ready || tab !== 'Evaluation') return;
    let cancelled = false;
    api(`/repositories/${selected}/learning-cases?status=pending`)
      .then((cases) => {
        if (!cancelled) setLearningCases(cases);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [selected, ready, tab, learningSaved]);
  useEffect(() => {
    if (!ready) return;
    const java = repo.stats.java_files && !repo.stats.python_files;
    setRunner(java ? (repo.name === 'mockito' ? 'gradle' : 'maven') : 'python');
    setImage(java ? `devpilot-java-${repo.name}:local` : 'devpilot-runner:local');
    setTarget(
      repo.name === 'petclinic'
        ? 'OwnerControllerTests'
        : repo.name === 'commons-lang'
          ? 'StringUtilsTest'
          : repo.name === 'mockito'
            ? 'org.mockito.internal.util.MockUtilTest'
            : 'tests',
    );
    let cancelled = false;
    Promise.all([
      api(`/repositories/${selected}/files`),
      api(`/repositories/${selected}/graph`),
      api(`/repositories/${selected}/history`),
    ])
      .then(([f, g, h]) => {
        if (cancelled) return;
        setFiles(f);
        setGraph(g);
        setHistory(h);
        setNodeId(g.nodes.find((n) => n.kind === 'function')?.id || g.nodes[0]?.id);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [selected, ready]);
  useEffect(() => {
    if (!ready || !health?.langgraph_enabled) return;
    let cancelled = false;
    api(`/repositories/${selected}/guided-repairs?status=review`)
      .then((runs) => {
        if (cancelled || !runs.length) return;
        const pending = runs[0];
        setGuidedRun(pending);
        setProposal(pending.result.draft);
        setPatch(pending.result.draft.patch);
        setGeneratedTests(pending.result.draft.extra_tests);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [selected, ready, health?.langgraph_enabled]);
  useEffect(() => {
    if (!ready || tab !== 'Coverage') return;
    let cancelled = false;
    api(
      `/repositories/${selected}/coverage?status=${coverageStatus}&limit=100&offset=${coverageOffset}`,
    )
      .then((report) => {
        if (!cancelled) setCoverage(report);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [selected, ready, tab, coverageStatus, coverageOffset]);
  useEffect(() => {
    if (!ready || !file?.path) return;
    let cancelled = false;
    setRelatedTests(null);
    api(`/repositories/${selected}/related-tests?path=${encodeURIComponent(file.path)}`)
      .then((links) => {
        if (!cancelled) setRelatedTests(links);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [selected, ready, file?.path]);
  useEffect(() => {
    if (!run?.id || run.status !== 'running') return;
    let cancelled = false;
    const t = setInterval(
      () =>
        api(`/executions/${run.id}`)
          .then((r) => {
            if (!cancelled) setRun(r);
          })
          .catch((e) => {
            if (!cancelled) setError(e.message);
          }),
      1500,
    );
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [run?.id, run?.status]);
  useEffect(() => {
    if (!guidedRun?.id || guidedRun.status !== 'running') return;
    let cancelled = false;
    const t = setInterval(
      () =>
        api(`/guided-repairs/${guidedRun.id}`)
          .then((r) => {
            if (!cancelled) setGuidedRun(r);
          })
          .catch((e) => {
            if (!cancelled) setError(e.message);
          }),
      1500,
    );
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [guidedRun?.id, guidedRun?.status]);
  async function addRepo(demo = false) {
    setBusy(true);
    setError('');
    try {
      const r = await api(demo ? '/demo' : '/repositories', demo ? {} : { source });
      await refresh();
      setSelected(r.id);
      setModal(false);
      setSource('');
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function ask(q = question) {
    if (!q.trim() || !ready || busy) return;
    setQuestion(q);
    setBusy(true);
    setError('');
    const current = selected;
    try {
      const r = await api(`/repositories/${current}/ask`, {
        question: q,
        mode,
        use_model: useModel,
        deep,
      });
      setResult(r);
      setLearningQueuedRun('');
      setHistory(await api(`/repositories/${current}/history`));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function openFile(path) {
    try {
      setFile(await api(`/repositories/${selected}/file?path=${encodeURIComponent(path)}`));
      setTab('Code explorer');
    } catch (e) {
      setError(e.message);
    }
  }
  async function execute() {
    setBusy(true);
    setError('');
    try {
      setRun(
        await api(`/repositories/${selected}/execute`, {
          target,
          image,
          runner,
          patch: patch || null,
          extra_tests: generatedTests,
          timeout: 120,
        }),
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function generateProposal() {
    if (!proposalRequest.trim()) return;
    setBusy(true);
    setError('');
    try {
      const draft = await api(`/repositories/${selected}/propose`, { request: proposalRequest });
      setGuidedRun(null);
      setProposal(draft);
      setPatch(draft.patch);
      setGeneratedTests(draft.extra_tests);
      const testPaths = Object.keys(draft.extra_tests);
      if (draft.language === 'java' && testPaths.length === 1) {
        const classPath = testPaths[0].split('src/test/java/')[1];
        if (classPath) {
          setTarget(
            runner === 'gradle'
              ? classPath.replace(/\.java$/, '').replaceAll('/', '.')
              : classPath
                  .split('/')
                  .at(-1)
                  .replace(/\.java$/, ''),
          );
        }
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function generateGuidedProposal() {
    if (!proposalRequest.trim()) return;
    setBusy(true);
    setError('');
    try {
      const guided = await api(`/repositories/${selected}/guided-repairs`, {
        request: proposalRequest,
        image,
        runner,
        target,
        timeout: 120,
      });
      setGuidedRun(guided);
      const draft = guided.result.draft;
      setProposal(draft);
      setPatch(draft.patch);
      setGeneratedTests(draft.extra_tests);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function reviewGuidedProposal(approved) {
    setBusy(true);
    setError('');
    try {
      const updated = await api(`/repositories/${selected}/guided-repairs/${guidedRun.id}/review`, {
        approved,
      });
      setGuidedRun({ ...guidedRun, ...updated });
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function evaluate() {
    setBusy(true);
    setError('');
    try {
      setEvaluation(
        await api(`/repositories/${selected}/evaluate`, { cases: JSON.parse(evalText) }),
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function queueAnswerForReview() {
    if (!result?.id || !question.trim()) return;
    setBusy(true);
    setError('');
    try {
      await api(`/repositories/${selected}/learning-cases`, {
        question,
        investigation_id: result.id,
      });
      setLearningQueuedRun(result.id);
      setLearningSaved((value) => !value);
      setTab('Evaluation');
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  function selectLearningCase(item) {
    setActiveLearningCase(item);
    setLearningSplit(item.repository_split || 'development');
    setLearningAnswerable(true);
    setLearningSymbols('');
    setLearningAnswer('');
    setLearningSources('[]');
    setLearningNotes('');
    setLearningAnswerCorrect(null);
    setLearningClaimsSupported(null);
    setLearningAbstention(null);
  }
  async function submitLearningReview() {
    if (!activeLearningCase) return;
    setBusy(true);
    setError('');
    try {
      const expectedSymbols = learningAnswerable
        ? learningSymbols
            .split(/[\n,]/)
            .map((symbol) => symbol.trim())
            .filter(Boolean)
        : [];
      const sourceRefs = learningAnswerable ? JSON.parse(learningSources) : [];
      await api(`/repositories/${selected}/learning-cases/${activeLearningCase.id}/review`, {
        answerable: learningAnswerable,
        expected_symbols: expectedSymbols,
        expected_answer: learningAnswerable ? learningAnswer : null,
        source_refs: sourceRefs,
        answer_correct: activeLearningCase.initial_result?.generated ? learningAnswerCorrect : null,
        all_claims_supported: activeLearningCase.initial_result?.generated
          ? learningClaimsSupported
          : null,
        appropriate_abstention: activeLearningCase.initial_result ? learningAbstention : null,
        split: learningSplit,
        notes: learningNotes,
      });
      setActiveLearningCase(null);
      setLearningSaved((value) => !value);
    } catch (e) {
      setError(e instanceof SyntaxError ? 'Source references must be valid JSON.' : e.message);
    } finally {
      setBusy(false);
    }
  }
  const connected = graph.edges.filter((e) => e.source === nodeId || e.target === nodeId);
  const activeNode = graph.nodes.find((n) => n.id === nodeId);
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="DevPilot home">
          <span className="brand-mark">
            <Command size={20} />
          </span>
          devpilot<span className="brand-dot">.</span>
        </a>
        <div className="workspace-label">
          <span className="avatar">D</span>
          <div>
            Development workspace<small>Local environment</small>
          </div>
          <span className="online-dot" />
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          {tabs.map(([name, Icon]) => (
            <button
              key={name}
              onClick={() => setTab(name)}
              className={'nav-item ' + (tab === name ? 'active' : '')}
            >
              <Icon size={17} />
              {name}
              {tab === name && <span className="nav-active-dot" />}
            </button>
          ))}
        </nav>
        <div className="nav-label repos-label">
          REPOSITORIES
          <button aria-label="Add repository" onClick={() => setModal(true)}>
            <Plus size={16} />
          </button>
        </div>
        <div className="repo-nav">
          {repos.length ? (
            repos.map((r) => (
              <button
                key={r.id}
                className={selected === r.id ? 'selected' : ''}
                onClick={() => setSelected(r.id)}
              >
                <GitBranch size={15} />
                <span>{r.name}</span>
                <i className={r.status === 'ready' ? 'dot-green' : 'dot-amber'} />
              </button>
            ))
          ) : (
            <p>
              No repositories yet.
              <br />
              Add one to get started.
            </p>
          )}
        </div>
        <div className="sidebar-bottom">
          <div className="local-note">
            <ShieldCheck size={17} />
            <div>
              Your code. Your workspace.<small>Snapshots stored on this Mac.</small>
            </div>
          </div>
          <button className="settings-button" onClick={() => setTab('Settings')}>
            <Settings2 size={17} />
            Environment & providers
            <ArrowUpRight size={14} />
          </button>
        </div>
      </aside>
      <main>
        <header>
          <div className="breadcrumbs">
            Workspace
            <ChevronRight size={13} />
            <span>{tab}</span>
          </div>
          <div className="header-right">
            <span className="local-badge">
              <i />
              LOCAL
            </span>
            <a
              href="/docs"
              onClick={(e) => {
                e.preventDefault();
                window.open('/docs', '_blank');
              }}
            >
              API docs
              <ArrowUpRight size={13} />
            </a>
            <span className="user-avatar">D</span>
          </div>
        </header>
        <div className="page">
          <div className="page-heading">
            <div>
              <div className="eyebrow">REPOSITORY INTELLIGENCE</div>
              <h1>{tab === 'Investigate' ? 'Understand the whole picture.' : tab}</h1>
              <p>
                {tab === 'Investigate'
                  ? 'Follow the code. Find the connections. Build with evidence.'
                  : 'Explore your repository with source-grounded evidence.'}
              </p>
            </div>
            <button className="button primary" onClick={() => setModal(true)}>
              <Plus size={16} />
              Add repository
            </button>
          </div>
          {error && (
            <div role="alert" className="error-banner">
              <AlertCircle size={17} />
              {error}
              <button onClick={() => setError('')} aria-label="Dismiss error">
                <X size={16} />
              </button>
            </div>
          )}
          {repo && (
            <div className="repo-strip">
              <span className="repo-icon">
                <GitBranch size={21} />
              </span>
              <div className="repo-title">
                {repo.name}
                <span>
                  {repo.commit_id ? repo.commit_id.slice(0, 8) : 'Local snapshot'}
                  <span className="separator">/</span>
                  {repo.stats?.python_files && repo.stats?.java_files
                    ? 'Python + Java'
                    : repo.stats?.java_files
                      ? 'Java'
                      : 'Python'}
                </span>
              </div>
              <span className={'status ' + (ready ? 'ready' : 'pending')}>
                {ready ? <Check size={12} /> : <Loader2 size={12} className="spin" />}
                {repo.status}
              </span>
              <div className="repo-strip-right">
                <span>
                  <Files size={14} />
                  {repo.stats.files || 0} files
                </span>
                <span>
                  <Braces size={14} />
                  {repo.stats.symbols || 0} symbols
                </span>
                <span>
                  <GitFork size={14} />
                  {repo.stats.edges || 0} relationships
                </span>
              </div>
            </div>
          )}
          {repo && !ready && (
            <div className="loading-card">
              <Activity size={25} />
              <h3>{repo.progress}</h3>
              <p>{repo.error || 'Parsing source files and connecting the repository structure.'}</p>
            </div>
          )}
          {!repo && tab !== 'Settings' && (
            <div className="welcome">
              <div className="welcome-graphic">
                <GitFork size={48} />
              </div>
              <div className="eyebrow">A BETTER WAY TO KNOW YOUR CODE</div>
              <h2>
                Every answer starts
                <br />
                with a connection.
              </h2>
              <p>
                Bring in a repository to explore its functions, trace dependencies,
                <br />
                and ask questions backed by the source.
              </p>
              <div className="button-row">
                <button className="button primary" onClick={() => setModal(true)}>
                  Connect a repository
                  <ArrowRight size={16} />
                </button>
                <button className="button" disabled={busy} onClick={() => addRepo(true)}>
                  {busy ? <Loader2 size={16} className="spin" /> : <Code2 size={16} />}Try the
                  example
                </button>
              </div>
              <div className="welcome-steps">
                <span>
                  01 <b>Index your code</b>
                </span>
                <span>
                  02 <b>Trace relationships</b>
                </span>
                <span>
                  03 <b>Find the evidence</b>
                </span>
              </div>
            </div>
          )}
          {ready && tab === 'Investigate' && (
            <div className="investigate-layout">
              <section>
                <div className="question-card">
                  <div className="card-label">
                    <span>
                      <Search size={16} />
                      Ask your codebase
                    </span>
                    <span className="tiny-tag">
                      {health?.model_configured ? 'MODEL CONNECTED' : 'RETRIEVAL MODE'}
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
                          <option value="semantic" disabled={!health?.embedding_configured}>
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
                            ? 'Repository answer'
                            : 'Evidence report'}
                      </b>
                      <span className="time">
                        <Clock size={13} />
                        {(result.elapsed_ms / 1000).toFixed(2)}s
                      </span>
                    </div>
                    {result.warning && <div className="warning">{result.warning}</div>}
                    <div className="answer-text">{result.answer}</div>
                    <div className="result-meta">
                      <span>Execution: not run</span>
                      {result.workflow && (
                        <span>LangGraph · {result.workflow.retrieval_passes} search pass(es)</span>
                      )}
                      {result.generated && <span>Citation support: not verified</span>}
                      <span>
                        {result.semantic_used
                          ? 'Semantic + structural context'
                          : 'Text-based context'}
                      </span>
                      {result.usage?.total_tokens && (
                        <span>{result.usage.total_tokens} tokens</span>
                      )}
                      {result.generation_diagnostics?.attempt_count > 0 && (
                        <span>
                          Model {result.generation_diagnostics.attempt_count} call
                          {result.generation_diagnostics.attempt_count === 1 ? '' : 's'} ·{' '}
                          {(result.generation_diagnostics.total_request_ms / 1000).toFixed(1)}s
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
                          <button onClick={() => openFile(s.path)}>
                            Open file
                            <ArrowUpRight size={13} />
                          </button>
                        </div>
                        <pre>{s.source}</pre>
                        {s.truncated && (
                          <small className="truncate">
                            Excerpt truncated to fit the context budget.
                          </small>
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
                    {repo.stats.python_files && repo.stats.java_files
                      ? 'Python AST + Java Tree-sitter'
                      : repo.stats.java_files
                        ? 'Java Tree-sitter'
                        : 'Python AST'}
                  </b>
                </div>
                <div className="context-row">
                  <span>Search</span>
                  <b>
                    {repo.stats.embedding_status === 'ready' ? 'Embeddings + text' : 'Text + graph'}
                  </b>
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
                    Source citations show what the answer used. Test results show what actually ran.
                  </p>
                  <ShieldCheck size={24} />
                </div>
              </aside>
            </div>
          )}
          {ready && tab === 'Code explorer' && (
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
                          <small>
                            {link.confidence === 'static' ? 'Static reference' : 'Name match'}
                          </small>
                        </button>
                      ))}
                    </div>
                    <small>{relatedTests.notice}</small>
                  </div>
                )}
                {file ? (
                  <div className="source-lines">
                    {file.content.split('\n').map((l, i) => (
                      <div key={i}>
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
          )}
          {ready && tab === 'Coverage' && (
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
                      Ignored directories are recorded by directory name; their contents are not
                      scanned. {coverage.summary.entries_capped && 'The path list reached its cap.'}
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
          )}
          {ready && tab === 'Dependencies' && (
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
                  Calls with unresolved targets are counted in the snapshot summary and are not
                  drawn as confirmed relationships.
                </p>
              </div>
            </div>
          )}
          {ready && tab === 'Verification' && (
            <div className="verification">
              <div className="section-title">
                EXECUTION WORKSPACE<span>Disposable checkout</span>
              </div>
              <p>
                Run a repository’s tests in an isolated container. Optionally compare the same tests
                before and after a unified diff.
              </p>
              <label>
                Change request for model proposal
                <textarea
                  className="patch-input"
                  placeholder="Describe the behavior to test and fix; include relevant function names."
                  value={proposalRequest}
                  onChange={(e) => setProposalRequest(e.target.value)}
                />
              </label>
              <button
                className="button"
                disabled={busy || !health?.model_configured || !proposalRequest.trim()}
                onClick={generateProposal}
              >
                {busy ? <Loader2 className="spin" size={16} /> : <Braces size={16} />}
                Generate review draft
              </button>
              {health?.langgraph_enabled && (
                <button
                  className="button"
                  disabled={busy || !health?.model_configured || !proposalRequest.trim()}
                  onClick={generateGuidedProposal}
                >
                  {busy ? <Loader2 className="spin" size={16} /> : <Braces size={16} />}
                  Start guided repair
                </button>
              )}
              {proposal && (
                <div className="run-result">
                  <b>Unverified proposal</b>
                  <p>{proposal.summary}</p>
                  <p className="muted-note">
                    {Object.keys(proposal.extra_tests).length} generated test file(s). Review the
                    patch and tests before running verification.
                  </p>
                  {proposal.ignored_model_patch && (
                    <p className="muted-note">
                      The model also supplied a raw diff. DevPilot ignored it and built the shown
                      patch from exact source edits.
                    </p>
                  )}
                  {Object.entries(proposal.extra_tests).map(([path, content]) => (
                    <div key={path}>
                      <b>{path}</b>
                      <pre>{content}</pre>
                    </div>
                  ))}
                </div>
              )}
              {guidedRun && (
                <div className="run-result">
                  <b>Guided repair · {guidedRun.status}</b>
                  {guidedRun.status === 'review' && (
                    <>
                      <p>
                        Review the generated test above and patch below. Approval runs the saved
                        draft in Docker; it does not edit the indexed repository.
                      </p>
                      <button
                        className="button primary"
                        disabled={busy || !health?.docker?.available}
                        onClick={() => reviewGuidedProposal(true)}
                      >
                        Approve and verify
                      </button>
                      <button
                        className="button"
                        disabled={busy}
                        onClick={() => reviewGuidedProposal(false)}
                      >
                        Decline draft
                      </button>
                    </>
                  )}
                  {guidedRun.result?.error && (
                    <div className="warning">{guidedRun.result.error}</div>
                  )}
                  {guidedRun.result?.outcome && (
                    <p>
                      Outcome: {guidedRun.result.outcome}. A passing transition verifies only the
                      selected generated test.
                    </p>
                  )}
                  {['baseline', 'patched'].map(
                    (key) =>
                      guidedRun.result?.[key] && (
                        <div key={key}>
                          <h3>
                            {key} · {guidedRun.result[key].status}
                          </h3>
                          <pre>{guidedRun.result[key].output}</pre>
                        </div>
                      ),
                  )}
                </div>
              )}
              {!health?.docker?.available && (
                <div className="warning">
                  <AlertCircle size={16} /> {health?.docker?.reason} Install and start Docker, build
                  the runner image, then refresh this page.
                </div>
              )}
              <div className="form-row">
                <label>
                  Test runner
                  <select value={runner} onChange={(e) => setRunner(e.target.value)}>
                    <option value="python">Python / pytest</option>
                    <option value="maven">Java / Maven</option>
                    <option value="gradle">Java / Gradle</option>
                  </select>
                </label>
                <label>
                  Runner image
                  <input value={image} onChange={(e) => setImage(e.target.value)} />
                </label>
                <label>
                  Test target
                  <input value={target} onChange={(e) => setTarget(e.target.value)} />
                </label>
              </div>
              <label>
                Proposed patch <span className="muted">(optional unified diff)</span>
                <textarea
                  className="patch-input"
                  placeholder={'diff --git a/path.py b/path.py\n…'}
                  value={patch}
                  disabled={guidedRun?.status === 'review'}
                  onChange={(e) => setPatch(e.target.value)}
                />
              </label>
              <div className="execution-footer">
                <span>
                  <ShieldCheck size={14} />
                  Network disabled · 1 GB memory · 120s timeout
                </span>
                <button
                  className="button primary"
                  disabled={busy || run?.status === 'running' || !health?.docker?.available}
                  onClick={execute}
                >
                  {run?.status === 'running' ? (
                    <Loader2 className="spin" size={16} />
                  ) : (
                    <Terminal size={16} />
                  )}
                  Run verification
                </button>
              </div>
              <p className="muted-note">
                The image must already contain pytest and the repository’s dependencies. Passing
                tests support only the behaviours they exercise.
              </p>
              {run && (
                <div className="run-result">
                  <div className="section-title">
                    RUN {run.id.slice(0, 8)}
                    <span>{run.status}</span>
                  </div>
                  {run.result?.error && <div className="warning">{run.result.error}</div>}
                  {['baseline', 'patched'].map(
                    (k) =>
                      run.result?.[k] && (
                        <div key={k}>
                          <h3>
                            {k} · {run.result[k].status}
                          </h3>
                          <pre>{run.result[k].output}</pre>
                        </div>
                      ),
                  )}
                </div>
              )}
            </div>
          )}
          {ready && tab === 'Evaluation' && (
            <div className="verification">
              <div className="section-title">
                RETRIEVAL EXPERIMENT<span>Same snapshot · Same questions</span>
              </div>
              <p>
                Compare text search, graph expansion, and hybrid retrieval with labelled supporting
                symbols. These metrics measure retrieval, not answer correctness.
              </p>
              <label>
                Evaluation cases
                <textarea
                  className="eval-input"
                  value={evalText}
                  onChange={(e) => setEvalText(e.target.value)}
                />
              </label>
              <button className="button primary" disabled={busy} onClick={evaluate}>
                {busy ? <Loader2 size={16} className="spin" /> : <Beaker size={16} />}Run comparison
              </button>
              {evaluation && (
                <>
                  <table>
                    <thead>
                      <tr>
                        <th>Strategy</th>
                        <th>Recall @ 8</th>
                        <th>Precision @ 8</th>
                        <th>MRR</th>
                      </tr>
                    </thead>
                    <tbody>
                      {evaluation.results.map((r) => (
                        <tr key={r.mode}>
                          <td>{r.mode}</td>
                          <td>{(r.recall * 100).toFixed(1)}%</td>
                          <td>{(r.precision * 100).toFixed(1)}%</td>
                          <td>{r.mrr.toFixed(3)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="muted-note">{evaluation.note}</p>
                  <button
                    className="button"
                    onClick={() => {
                      const a = document.createElement('a');
                      const url = URL.createObjectURL(
                        new Blob([JSON.stringify(evaluation, null, 2)], {
                          type: 'application/json',
                        }),
                      );
                      a.href = url;
                      a.download = 'devpilot-evaluation.json';
                      a.click();
                      URL.revokeObjectURL(url);
                    }}
                  >
                    Export results
                    <ArrowUpRight size={15} />
                  </button>
                </>
              )}
              <div className="panel-divider" />
              <div className="section-title">
                REVIEW QUEUE<span>{learningCases.length} pending</span>
              </div>
              <p>
                Save difficult investigations here. Only source-checked examples you mark as
                reviewed can be exported into the development or holdout datasets.
              </p>
              {learningCases.length ? (
                <div className="learning-case-list">
                  {learningCases.map((item) => (
                    <button
                      className={
                        'learning-case-item ' +
                        (activeLearningCase?.id === item.id ? 'selected' : '')
                      }
                      key={item.id}
                      onClick={() => selectLearningCase(item)}
                    >
                      <span>{item.question}</span>
                      <small>
                        {item.repository_split || 'split not assigned'} · snapshot{' '}
                        {item.snapshot.slice(0, 10)}
                      </small>
                    </button>
                  ))}
                </div>
              ) : (
                <p className="muted-note">No pending reviews for this repository.</p>
              )}
              {activeLearningCase && (
                <div className="learning-review">
                  <div className="section-title">
                    REVIEW THIS CASE<span>Check the indexed source before saving labels</span>
                  </div>
                  <p className="learning-question">{activeLearningCase.question}</p>
                  {activeLearningCase.initial_result && (
                    <details className="learning-original">
                      <summary>DevPilot response and retrieved symbols</summary>
                      <p>{activeLearningCase.initial_result.answer}</p>
                      <ul>
                        {activeLearningCase.initial_result.evidence.map((item) => (
                          <li key={`${item.qualified}:${item.start_line}`}>
                            <code>{item.qualified}</code> · {item.path}:{item.start_line}–
                            {item.end_line}
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                  <label>
                    Case answerability
                    <select
                      value={learningAnswerable ? 'answerable' : 'unanswerable'}
                      onChange={(event) =>
                        setLearningAnswerable(event.target.value === 'answerable')
                      }
                    >
                      <option value="answerable">Answerable from this snapshot</option>
                      <option value="unanswerable">Not answerable from this snapshot</option>
                    </select>
                  </label>
                  <label>
                    Repository split
                    <select
                      value={learningSplit}
                      disabled={Boolean(activeLearningCase.repository_split)}
                      onChange={(event) => setLearningSplit(event.target.value)}
                    >
                      <option value="development">Development · tune on these repos</option>
                      <option value="holdout">Holdout · reserve this whole repo</option>
                    </select>
                  </label>
                  {learningAnswerable && (
                    <>
                      <label>
                        Expected qualified symbols · one per line
                        <textarea
                          value={learningSymbols}
                          onChange={(event) => setLearningSymbols(event.target.value)}
                          placeholder="parcel.pricing.calculate_quote"
                        />
                      </label>
                      <label>
                        Reviewed expected answer
                        <textarea
                          value={learningAnswer}
                          onChange={(event) => setLearningAnswer(event.target.value)}
                        />
                      </label>
                      <label>
                        Source references · JSON array within the symbol ranges
                        <textarea
                          value={learningSources}
                          onChange={(event) => setLearningSources(event.target.value)}
                          placeholder='[{"qualified":"pkg.function","path":"src/file.py","start_line":10,"end_line":20}]'
                        />
                      </label>
                    </>
                  )}
                  {activeLearningCase.initial_result?.generated && (
                    <div className="learning-checks">
                      <label>
                        Generated answer correct?
                        <select
                          value={
                            learningAnswerCorrect === null ? '' : String(learningAnswerCorrect)
                          }
                          onChange={(event) =>
                            setLearningAnswerCorrect(
                              event.target.value === '' ? null : event.target.value === 'true',
                            )
                          }
                        >
                          <option value="">Review required</option>
                          <option value="true">Yes</option>
                          <option value="false">No</option>
                        </select>
                      </label>
                      <label>
                        Every claim supported by its cited source?
                        <select
                          value={
                            learningClaimsSupported === null ? '' : String(learningClaimsSupported)
                          }
                          onChange={(event) =>
                            setLearningClaimsSupported(
                              event.target.value === '' ? null : event.target.value === 'true',
                            )
                          }
                        >
                          <option value="">Review required</option>
                          <option value="true">Yes</option>
                          <option value="false">No</option>
                        </select>
                      </label>
                    </div>
                  )}
                  {activeLearningCase.initial_result && (
                    <label>
                      Did the response answer or abstain appropriately?
                      <select
                        value={learningAbstention === null ? '' : String(learningAbstention)}
                        onChange={(event) =>
                          setLearningAbstention(
                            event.target.value === '' ? null : event.target.value === 'true',
                          )
                        }
                      >
                        <option value="">Review required</option>
                        <option value="true">Yes</option>
                        <option value="false">No</option>
                      </select>
                    </label>
                  )}
                  <label>
                    Reviewer notes · explain how you checked the source
                    <textarea
                      value={learningNotes}
                      onChange={(event) => setLearningNotes(event.target.value)}
                    />
                  </label>
                  <button className="button primary" disabled={busy} onClick={submitLearningReview}>
                    {busy ? <Loader2 size={15} className="spin" /> : <Check size={15} />}
                    Save reviewed case
                  </button>
                </div>
              )}
            </div>
          )}
          {tab === 'Settings' && (
            <div className="verification">
              <div className="section-title">
                ENVIRONMENT STATUS<span>Credentials stay on the backend</span>
              </div>
              <div className="context-row">
                <span>Model provider</span>
                <b>{health?.model_configured ? health.model : 'Not configured'}</b>
              </div>
              <div className="context-row">
                <span>Semantic embeddings</span>
                <b>{health?.embedding_configured ? 'Configured' : 'Not configured'}</b>
              </div>
              <div className="context-row">
                <span>Docker engine</span>
                <b>{health?.docker?.available ? 'Available' : 'Unavailable'}</b>
              </div>
              <p>
                Configure an API-compatible provider using environment variables before starting the
                backend. Re-index a repository after enabling embeddings.
              </p>
              <pre>
                {
                  'DEVPILOT_LLM_BASE_URL=https://your-provider/v1\nDEVPILOT_LLM_MODEL=your-model\nDEVPILOT_API_KEY=your-key\nDEVPILOT_EMBEDDING_MODEL=your-embedding-model'
                }
              </pre>
              <p className="muted-note">
                Without a provider, code browsing, text retrieval, dependency expansion, and
                retrieval evaluation work locally. With a provider, selected source excerpts are
                sent to your configured endpoint.
              </p>
            </div>
          )}
          <footer>
            <span>
              <span className="online-dot" />
              DevPilot local workspace
            </span>
            <span>Structure-aware. Evidence-first.</span>
          </footer>
        </div>
      </main>
      {modal && (
        <div className="modal-overlay" onClick={() => setModal(false)}>
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Connect a repository"
            className="modal"
            onClick={(e) => e.stopPropagation()}
          >
            <button className="modal-close" onClick={() => setModal(false)} aria-label="Close">
              <X size={18} />
            </button>
            <span className="repo-icon">
              <GitBranch size={25} />
            </span>
            <h2>Connect your repository</h2>
            <p>
              Index a public GitHub repository or a local directory. DevPilot creates a separate
              snapshot for analysis.
            </p>
            <label>
              GitHub URL or local path
              <input
                autoFocus
                placeholder="https://github.com/psf/requests"
                value={source}
                onChange={(e) => setSource(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && source.trim()) addRepo();
                }}
              />
            </label>
            <div className="modal-note">
              <ShieldCheck size={16} />
              Source files are read, never executed during indexing.
            </div>
            {error && <div className="warning">{error}</div>}
            <button
              className="button primary full"
              disabled={busy || !source.trim()}
              onClick={() => addRepo()}
            >
              {busy ? <Loader2 size={16} className="spin" /> : <Plus size={16} />}Create snapshot
            </button>
            <button className="demo-link" disabled={busy} onClick={() => addRepo(true)}>
              Or explore the included example
              <ArrowRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
