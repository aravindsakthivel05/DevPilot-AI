import { api } from './api';
import {
  ErrorsPage,
  SuggestionsPage,
  GraphPage,
  RetrievalPage,
  ResearchEvaluationPage,
} from './components/ResearchPages';
import EvaluationPage from './components/EvaluationPage';
import LegacyVerificationPage from './components/LegacyVerificationPage';

import CoveragePage from './components/CoveragePage';
import ExplorerPage from './components/ExplorerPage';
import InvestigatePage from './components/InvestigatePage';
import { useEffect, useState } from 'react';

import {
  ArrowUpRight,
  ArrowRight,
  GitBranch,
  GitFork,
  Search,
  Layers,
  Plus,
  Check,
  ChevronRight,
  Code2,
  Files,
  Activity,
  Settings2,
  Loader2,
  X,
  Beaker,
  ShieldCheck,
  AlertCircle,
  Braces,
  Command,
} from 'lucide-react';

const tabs = [
  ['Investigate', Search],
  ['Code explorer', Files],
  ['Coverage', Layers],
  ['Dependencies', GitFork],
  ['Error analysis', AlertCircle],
  ['Suggestions', Braces],
  ['Retrieval diagnostics', Search],
  ['Research experiments', Beaker],
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
  const [indexStatus, setIndexStatus] = useState(null);
  const [providerStatus, setProviderStatus] = useState(null);
  const [probingProvider, setProbingProvider] = useState(false);
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
    setIndexStatus(null);
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
      Promise.resolve({ nodes: [], edges: [] }),
      api(`/repositories/${selected}/history`),
      api(`/repositories/${selected}/index-status`),
    ])
      .then(([f, g, h, status]) => {
        if (cancelled) return;
        setFiles(f);
        setGraph(g);
        setHistory(h);
        setIndexStatus(status);
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
    if (!ready || !health?.langgraph_enabled || !health?.legacy_execution_enabled) return;
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
  }, [selected, ready, health?.langgraph_enabled, health?.legacy_execution_enabled]);
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
  async function openFile(path, line) {
    try {
      setFile({
        ...(await api(`/repositories/${selected}/file?path=${encodeURIComponent(path)}`)),
        focusLine: Number(line) || null,
      });
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
          {tabs
            .filter(([name]) => name !== 'Verification' || health?.legacy_execution_enabled)
            .map(([name, Icon]) => (
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
                  {Object.keys(repo.stats?.languages || {})
                    .filter((language) => language !== 'text')
                    .join(' + ') ||
                    (repo.stats?.java_files
                      ? 'Java'
                      : repo.stats?.python_files
                        ? 'Python'
                        : 'Text snapshot')}
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
          {ready && indexStatus?.derived_index_current === false && (
            <div className="error-banner">
              <span>
                This snapshot uses an older structural index. Rebuild its stored files to enable the
                new analysis; create a new snapshot to include previously excluded file types.
              </span>
              <button
                className="button"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    await api(`/repositories/${selected}/rebuild-index`, { embeddings: true });
                    setRepos(await api('/repositories'));
                  } catch (e) {
                    setError(e.message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Rebuild index
              </button>
            </div>
          )}
          {ready && tab === 'Investigate' && (
            <InvestigatePage
              {...{
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
              }}
            />
          )}
          {ready && tab === 'Code explorer' && (
            <ExplorerPage {...{ file, files, openFile, query, relatedTests, setQuery }} />
          )}
          {ready && tab === 'Coverage' && (
            <CoveragePage
              {...{
                coverage,
                coverageOffset,
                coverageStatus,
                setCoverageOffset,
                setCoverageStatus,
              }}
            />
          )}
          {ready && tab === 'Dependencies' && (
            <GraphPage key={selected} repoId={selected} openFile={openFile} />
          )}
          {ready && tab === 'Verification' && health?.legacy_execution_enabled && (
            <LegacyVerificationPage
              {...{
                busy,
                execute,
                generateGuidedProposal,
                generateProposal,
                guidedRun,
                health,
                image,
                patch,
                proposal,
                proposalRequest,
                reviewGuidedProposal,
                run,
                runner,
                setImage,
                setPatch,
                setProposalRequest,
                setRunner,
                setTarget,
                target,
              }}
            />
          )}
          {ready && tab === 'Error analysis' && (
            <ErrorsPage key={selected} repoId={selected} openFile={openFile} />
          )}
          {ready && tab === 'Suggestions' && (
            <SuggestionsPage key={selected} repoId={selected} openFile={openFile} />
          )}
          {ready && tab === 'Retrieval diagnostics' && (
            <RetrievalPage key={selected} repoId={selected} openFile={openFile} />
          )}
          {ready && tab === 'Research experiments' && (
            <ResearchEvaluationPage key={selected} repoId={selected} />
          )}
          {ready && tab === 'Evaluation' && (
            <EvaluationPage
              {...{
                activeLearningCase,
                busy,
                evalText,
                evaluate,
                evaluation,
                learningAbstention,
                learningAnswer,
                learningAnswerCorrect,
                learningAnswerable,
                learningCases,
                learningClaimsSupported,
                learningNotes,
                learningSources,
                learningSplit,
                learningSymbols,
                selectLearningCase,
                setEvalText,
                setLearningAbstention,
                setLearningAnswer,
                setLearningAnswerCorrect,
                setLearningAnswerable,
                setLearningClaimsSupported,
                setLearningNotes,
                setLearningSources,
                setLearningSplit,
                setLearningSymbols,
                submitLearningReview,
              }}
            />
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
                <span>Core workflow</span>
                <b>Source analysis and unverified suggestions</b>
              </div>
              <button
                className="button"
                disabled={probingProvider}
                onClick={async () => {
                  setProbingProvider(true);
                  try {
                    setProviderStatus(await api('/provider-status?probe=true'));
                  } catch (e) {
                    setError(e.message);
                  } finally {
                    setProbingProvider(false);
                  }
                }}
              >
                {probingProvider ? 'Checking provider…' : 'Check provider readiness'}
              </button>
              {providerStatus && (
                <>
                  <div className="context-row">
                    <span>Generation check</span>
                    <b>{providerStatus.generation_probe}</b>
                  </div>
                  <div className="context-row">
                    <span>Embedding check</span>
                    <b>{providerStatus.embedding_probe}</b>
                  </div>
                  <div className="context-row">
                    <span>Configured context window</span>
                    <b>{providerStatus.context_window} tokens</b>
                  </div>
                  {providerStatus.generation_error && (
                    <p className="muted-note">{providerStatus.generation_error}</p>
                  )}
                  {providerStatus.embedding_error && (
                    <p className="muted-note">{providerStatus.embedding_error}</p>
                  )}
                  <details>
                    <summary>Local model runtime details</summary>
                    <pre>{JSON.stringify(providerStatus.loaded_models || [], null, 2)}</pre>
                  </details>
                </>
              )}
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
