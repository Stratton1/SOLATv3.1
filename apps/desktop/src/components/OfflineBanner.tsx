/**
 * Engine offline warning banner with retry and start controls.
 */

import type { ConnectionState } from "../hooks/useEngineHealth";

interface OfflineBannerProps {
  connectionState: ConnectionState;
  error?: string | null;
  retryCount?: number;
  nextRetryIn?: number | null;
  onRetry?: () => void;
  onStartEngine?: () => void;
  isStartingEngine?: boolean;
}

export function OfflineBanner({
  connectionState,
  error,
  retryCount = 0,
  nextRetryIn,
  onRetry,
  onStartEngine,
  isStartingEngine = false,
}: OfflineBannerProps) {
  if (connectionState === "connected") {
    return null;
  }

  const isConnecting = connectionState === "connecting";
  const isRetrying = connectionState === "retrying";

  return (
    <div className="offline-banner">
      <div className="offline-content">
        <span className="offline-icon">
          {isConnecting ? "\u27F3" : isRetrying ? "\u23F3" : "\u26A0"}
        </span>

        <div className="offline-text-container">
          <span className="offline-text">
            {isStartingEngine
              ? "Starting engine..."
              : isConnecting
                ? "Connecting to engine..."
                : isRetrying
                  ? `Retrying connection...`
                  : "Engine offline \u2014 trading features unavailable"}
          </span>

          {!isConnecting && !isStartingEngine && (
            <span className="offline-hint">
              {error
                ? error
                : "Check that the SOLAT engine is running on port 8765"}
            </span>
          )}

          {isRetrying && nextRetryIn !== null && (
            <span className="offline-countdown">
              Next attempt in {nextRetryIn}s (attempt #{retryCount})
            </span>
          )}
        </div>

        <div className="offline-actions">
          {!isConnecting && onStartEngine && (
            <button
              className="offline-start-btn"
              onClick={onStartEngine}
              disabled={isStartingEngine}
            >
              {isStartingEngine ? "Starting..." : "Start Engine"}
            </button>
          )}

          {!isConnecting && onRetry && (
            <button className="offline-retry-btn" onClick={onRetry}>
              Retry Now
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default OfflineBanner;
