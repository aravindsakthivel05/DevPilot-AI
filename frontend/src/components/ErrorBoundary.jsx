import React from 'react';

export default class ErrorBoundary extends React.Component {
  state = { error: null };
  static getDerivedStateFromError(error) {
    return { error };
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <main style={{ padding: 40, background: '#fff', color: '#172033', minHeight: '100vh' }}>
        <h1>Unable to display DevPilot</h1>
        <p>
          Reload the page to retry. If this repeats, include the details below when reporting the
          issue.
        </p>
        <button onClick={() => window.location.reload()}>Reload</button>
        <details open>
          <summary>Error details</summary>
          <pre style={{ whiteSpace: 'pre-wrap' }}>
            {String(this.state.error)}
            {'\n'}
            {this.state.error.stack}
          </pre>
        </details>
      </main>
    );
  }
}
