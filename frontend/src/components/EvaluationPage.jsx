import { ArrowUpRight, Check, Loader2, Beaker } from 'lucide-react';
export default function EvaluationPage({
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
}) {
  return (
    <div className="verification">
      <div className="section-title">
        RETRIEVAL EXPERIMENT<span>Same snapshot · Same questions</span>
      </div>
      <p>
        Compare text search, graph expansion, and hybrid retrieval with labelled supporting symbols.
        These metrics measure retrieval, not answer correctness.
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
        Save difficult investigations here. Only source-checked examples you mark as reviewed can be
        exported into the development or holdout datasets.
      </p>
      {learningCases.length ? (
        <div className="learning-case-list">
          {learningCases.map((item) => (
            <button
              className={
                'learning-case-item ' + (activeLearningCase?.id === item.id ? 'selected' : '')
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
                    <code>{item.qualified}</code> · {item.path}:{item.start_line}–{item.end_line}
                  </li>
                ))}
              </ul>
            </details>
          )}
          <label>
            Case answerability
            <select
              value={learningAnswerable ? 'answerable' : 'unanswerable'}
              onChange={(event) => setLearningAnswerable(event.target.value === 'answerable')}
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
                  value={learningAnswerCorrect === null ? '' : String(learningAnswerCorrect)}
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
                  value={learningClaimsSupported === null ? '' : String(learningClaimsSupported)}
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
  );
}
