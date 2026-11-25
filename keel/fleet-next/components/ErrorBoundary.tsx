"use client";

// A failed feature must not take down the whole shell. Keep the failure
// visible and recoverable, and never hide the real error from diagnostics.

import React from "react";

interface State { error: Error | null }

export default class ErrorBoundary extends React.Component<
  { children: React.ReactNode; label: string },
  State
> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // Log locally only. No remote telemetry, no secrets in the message.
    console.error(`[keel:${this.props.label}]`, error, info.componentStack);
  }

  private reset = () => this.setState({ error: null });

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="keel-empty" role="alert" style={{ minHeight: "60vh" }}>
        <div className="keel-empty__icon" aria-hidden="true"><span style={{ fontSize: 22 }}>!</span></div>
        <h3>{this.props.label} could not be displayed</h3>
        <p>This surface hit an unexpected error. Your work and agent data are untouched — retry, or switch surfaces and come back.</p>
        <pre style={{ maxWidth: "80vw", overflow: "auto", fontSize: 11, color: "var(--k-muted)", whiteSpace: "pre-wrap" }}>
          {this.state.error.message}
        </pre>
        <button className="keel-btn keel-btn--secondary keel-btn--md" onClick={this.reset}>Retry this surface</button>
      </div>
    );
  }
}
