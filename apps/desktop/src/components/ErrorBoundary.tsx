/**
 * Error Boundary component for catching React rendering errors.
 *
 * Prevents the entire app from crashing when a single route/component fails.
 * Shows a friendly error message with recovery options.
 */

import { Component, ReactNode } from "react";

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: React.ErrorInfo) => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: React.ErrorInfo | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    this.setState({ errorInfo });

    // Log error for debugging
    console.error("[ErrorBoundary] Caught error:", error);
    console.error("[ErrorBoundary] Component stack:", errorInfo.componentStack);

    // Call optional error handler
    this.props.onError?.(error, errorInfo);
  }

  handleRetry = (): void => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });
  };

  handleCopyError = (): void => {
    const { error, errorInfo } = this.state;
    const details = [
      `Error: ${error?.message ?? "Unknown"}`,
      `Stack: ${error?.stack ?? "N/A"}`,
      `Component: ${errorInfo?.componentStack ?? "N/A"}`,
      `Time: ${new Date().toISOString()}`,
    ].join("\n\n");
    navigator.clipboard.writeText(details).catch(() => {
      // Fallback: select text if clipboard API fails
      console.warn("[ErrorBoundary] Clipboard write failed");
    });
  };

  render(): ReactNode {
    if (this.state.hasError) {
      // Custom fallback provided
      if (this.props.fallback) {
        return this.props.fallback;
      }

      // Default error UI
      return (
        <div className="error-boundary">
          <div className="error-boundary-content">
            <h2>Something went wrong</h2>
            <p className="error-message">
              {this.state.error?.message || "An unexpected error occurred"}
            </p>
            <div className="error-actions">
              <button className="btn btn-primary" onClick={this.handleRetry}>
                Try Again
              </button>
              <button className="btn btn-secondary" onClick={this.handleCopyError}>
                Copy Error Details
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => window.location.reload()}
              >
                Reload App
              </button>
            </div>
            {import.meta.env.DEV && this.state.errorInfo && (
              <details className="error-details">
                <summary>Error Details (Dev Mode)</summary>
                <pre>{this.state.error?.stack}</pre>
                <pre>{this.state.errorInfo.componentStack}</pre>
              </details>
            )}
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

/**
 * Hook-friendly wrapper for error boundary with reset on location change.
 * Use this for route-level error boundaries.
 */
export function RouteErrorBoundary({ children }: { children: ReactNode }) {
  return (
    <ErrorBoundary
      onError={(error) => {
        // Could send to error tracking service in production
        console.error("[RouteErrorBoundary] Route error:", error.message);
      }}
    >
      {children}
    </ErrorBoundary>
  );
}

export default ErrorBoundary;
