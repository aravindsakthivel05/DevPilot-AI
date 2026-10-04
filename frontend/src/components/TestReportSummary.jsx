export default function TestReportSummary({ report }) {
  if (!report?.available) {
    return (
      <p className="warning">
        No complete structured test report. This run cannot establish a passing test result.
      </p>
    );
  }
  return (
    <p className="muted-note">
      {report.total} tests · {report.passed} passed · {report.failures} failures · {report.errors}{' '}
      errors · {report.skipped} skipped
    </p>
  );
}
