import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertTriangle } from 'lucide-react';

interface Props {
  children: ReactNode;
  label?: string;
  compact?: boolean;
  resetKey?: unknown;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('UI error boundary caught:', error, info);
  }

  componentDidUpdate(prev: Props) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  reset = () => this.setState({ error: null });

  render() {
    if (this.state.error) {
      const msg = this.state.error.message || 'Unexpected error';
      if (this.props.compact) {
        return (
          <div className="flex items-center gap-2 rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-[11px] text-danger">
            <AlertTriangle size={12} className="shrink-0" />
            <span className="truncate" title={msg}>
              {this.props.label ? `${this.props.label}: ` : ''}{msg}
            </span>
            <button onClick={this.reset} className="ml-auto underline shrink-0">Retry</button>
          </div>
        );
      }
      return (
        <div className="h-full flex items-center justify-center p-6">
          <div className="card max-w-md w-full p-5 space-y-3">
            <div className="flex items-center gap-2 text-danger">
              <AlertTriangle size={16} />
              <span className="text-sm font-semibold">
                Something went wrong{this.props.label ? ` in ${this.props.label}` : ''}
              </span>
            </div>
            <p className="text-xs text-text-muted break-words font-mono">{msg}</p>
            <button onClick={this.reset} className="btn-outline text-xs">Try again</button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
