const labels = {
  supported: 'Evidence cited',
  insufficient_evidence: 'Missing evidence',
  outside_indexed_scope: 'Outside indexed scope',
};

export default function AnswerCoverage({ aspects = [] }) {
  if (!aspects.length) return null;
  return (
    <div className="aspect-coverage">
      <b>Question coverage</b>
      <ul>
        {aspects.map((aspect) => (
          <li key={aspect.aspect_id}>
            <span>{labels[aspect.status] || aspect.status}</span> — {aspect.question}
          </li>
        ))}
      </ul>
      <small>Citations identify evidence; factual correctness still requires review.</small>
    </div>
  );
}
