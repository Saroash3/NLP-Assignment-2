import { Component, type ReactNode } from "react";

/**
 * If a lazily loaded section fails (e.g. its chunk can't be downloaded), show nothing for that
 * section instead of letting the error blank the whole landing page -- the rest of the page and
 * the "Chat with Nova" buttons keep working.
 */
export class SectionBoundary extends Component<{ id: string; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    console.warn(`Section "${this.props.id}" failed to load and was skipped:`, error);
  }

  render() {
    return this.state.failed ? <section id={this.props.id} /> : this.props.children;
  }
}
