/**
 * Engine offline warning banner with retry controls.
 *
 * Displays a prominent banner when the trading engine is disconnected,
 * with countdown timer and manual retry button.
 */

import type { ConnectionState } from "../hooks/useEngineHealth";

interface OfflineBannerProps {
  connectionState: ConnectionState;
  error?: string | null;
  retryCount?: number;
  nextRetryIn?: number | null;
  onRetry?: () => void;
}

export function OfflineBanner({
  connectionState,
  error,
  retryCount = 0,
  nextRetryIn,
  onRetry,
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
          {isConnecting ? "⟳" : isRetrying ? "⏳" : "⚠"}
        </span>

        <div className="offline-text-container">
          <span className="offline-text">
            {isConnecting
              ? "Connecting to engine..."
              : isRetrying
                ? `Retrying connection...`
                : "Engine offline — trading features unavailable"}
          </span>

          {!isConnecting && (
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

        {!isConnecting && onRetry && (
          <button className="offline-retry-btn" onClick={onRetry}>
            Retry Now
          </button>
        )}
      </div>
    </div>
  );
}

export default OfflineBanner;
