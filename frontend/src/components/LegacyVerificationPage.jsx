import TestReportSummary from './TestReportSummary';
import { Terminal, Loader2, ShieldCheck, AlertCircle, Braces } from 'lucide-react';
export default function LegacyVerificationPage({
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
}) {
  return (
    <div className="verification">
      <div className="section-title">
        EXECUTION WORKSPACE<span>Disposable checkout</span>
      </div>
      <p>
        Run a repository’s tests in an isolated container. Optionally compare the same tests before
        and after a unified diff.
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
            {Object.keys(proposal.extra_tests).length} generated test file(s). Review the patch and
            tests before running verification.
          </p>
          {proposal.ignored_model_patch && (
            <p className="muted-note">
              The model also supplied a raw diff. DevPilot ignored it and built the shown patch from
              exact source edits.
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
                Review the generated test above and patch below. Approval runs the saved draft in
                Docker; it does not edit the indexed repository.
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
          {guidedRun.result?.error && <div className="warning">{guidedRun.result.error}</div>}
          {guidedRun.result?.outcome && (
            <p>
              Outcome: {guidedRun.result.outcome}. A passing transition verifies only the generated
              regression and the selected existing tests; other behavior remains unverified.
            </p>
          )}
          {['existing_baseline', 'baseline', 'patched', 'existing_patched'].map(
            (key) =>
              guidedRun.result?.[key] && (
                <div key={key}>
                  <h3>
                    {key} · {guidedRun.result[key].status}
                  </h3>
                  <TestReportSummary report={guidedRun.result[key].test_report} />
                  <pre>{guidedRun.result[key].output}</pre>
                </div>
              ),
          )}
        </div>
      )}
      {!health?.docker?.available && (
        <div className="warning">
          <AlertCircle size={16} /> {health?.docker?.reason} Install and start Docker, build the
          runner image, then refresh this page.
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
        The image must already contain pytest and the repository’s dependencies. Passing tests
        support only the behaviours they exercise.
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
                  <TestReportSummary report={run.result[k].test_report} />
                  <pre>{run.result[k].output}</pre>
                </div>
              ),
          )}
        </div>
      )}
    </div>
  );
}
