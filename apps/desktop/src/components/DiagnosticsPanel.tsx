/**
 * Diagnostics panel for system health monitoring.
 *
 * Shows:
 * - Market data mode (stream/poll) + stale indicator
 * - Current memory caches with row counts
 * - WS messages in/out per sec
 * - Rate-limiter headroom meters
 */

import { useState } from "react";
import { useDiagnostics } from "../hooks/useDiagnostics";

interface DiagnosticsPanelProps {
  defaultExpanded?: boolean;
}

export function DiagnosticsPanel({ defaultExpanded = false }: DiagnosticsPanelProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const { diagnostics, isLoading, error, refetch } = useDiagnostics(isExpanded, 5000);

  const toggleExpanded = () => {
    setIsExpanded(!isExpanded);
  };

  return (
    <div className="diagnostics-panel">
      <div className="diagnostics-header" onClick={toggleExpanded}>
        <span className="diagnostics-title">
          {isExpanded ? "▼" : "▶"} Diagnostics
        </span>
        {!isExpanded && diagnostics && (
          <span className="diagnostics-summary">
            <span className={`mode-badge ${diagnostics.stream_health.mode}`}>
              {diagnostics.stream_health.mode}
            </span>
            {diagnostics.stream_health.stale && (
              <span className="stale-badge">STALE</span>
            )}
          </span>
        )}
        <button
          className="refresh-btn"
          onClick={(e) => {
            e.stopPropagation();
            refetch();
          }}
          disabled={isLoading}
        >
          {isLoading ? "..." : "↻"}
        </button>
      </div>

      {isExpanded && (
        <div className="diagnostics-content">
          {error && <div className="diagnostics-error">{error}</div>}

          {diagnostics && (
            <>
              {/* Stream Health */}
              <div className="diagnostics-section">
                <h4>Stream Health</h4>
                <div className="diagnostics-grid">
                  <div className="diag-item">
                    <span className="diag-label">Mode</span>
                    <span className={`diag-value mode-${diagnostics.stream_health.mode}`}>
                      {diagnostics.stream_health.mode.toUpperCase()}
                    </span>
                  </div>
                  <div className="diag-item">
                    <span className="diag-label">Connected</span>
                    <span className={`diag-value ${diagnostics.stream_health.connected ? "positive" : "negative"}`}>
                      {diagnostics.stream_health.connected ? "Yes" : "No"}
                    </span>
                  </div>
                  <div className="diag-item">
                    <span className="diag-label">Stale</span>
                    <span className={`diag-value ${diagnostics.stream_health.stale ? "warning" : "positive"}`}>
                      {diagnostics.stream_health.stale ? "Yes" : "No"}
                    </span>
                  </div>
                  <div className="diag-item">
                    <span className="diag-label">Fallback Active</span>
                    <span className={`diag-value ${diagnostics.stream_health.fallback_active ? "warning" : ""}`}>
                      {diagnostics.stream_health.fallback_active ? "Yes" : "No"}
                    </span>
                  </div>
                  <div className="diag-item">
                    <span className="diag-label">Stream Failures</span>
                    <span className="diag-value">{diagnostics.stream_health.stream_failures}</span>
                  </div>
                  <div className="diag-item">
                    <span className="diag-label">Fallback Count</span>
                    <span className="diag-value">{diagnostics.stream_health.fallback_count}</span>
                  </div>
                </div>

                {diagnostics.stream_health.publisher_stats && (
                  <div className="diagnostics-substats">
                    <span>Quotes: {diagnostics.stream_health.publisher_stats.quotes_published ?? 0}</span>
                    <span>Throttled: {diagnostics.stream_health.publisher_stats.quotes_throttled ?? 0}</span>
                    <span>Bars: {diagnostics.stream_health.publisher_stats.bars_published ?? 0}</span>
                  </div>
                )}
              </div>

              {/* Memory / Caches */}
              <div className="diagnostics-section">
                <h4>Memory & Caches</h4>
                <div className="diag-item">
                  <span className="diag-label">Estimated Memory</span>
                  <span className="diag-value">{diagnostics.memory.estimated_mb.toFixed(2)} MB</span>
                </div>
                {Object.entries(diagnostics.memory.caches).map(([name, cache]) => (
                  <div key={name} className="cache-item">
                    <span className="cache-name">{cache.name || name}</span>
                    <div className="cache-bar">
                      <div
                        className="cache-fill"
                        style={{
                          width: `${Math.min(100, (cache.current_entries / cache.max_entries) * 100)}%`,
                        }}
                      />
                    </div>
                    <span className="cache-stats">
                      {cache.current_entries}/{cache.max_entries} ({cache.hit_rate.toFixed(1)}% hit)
                    </span>
                  </div>
                ))}
              </div>

              {/* WebSocket */}
              <div className="diagnostics-section">
                <h4>WebSocket</h4>
                <div className="diagnostics-grid">
                  <div className="diag-item">
                    <span className="diag-label">Connected Clients</span>
                    <span className="diag-value">{diagnostics.websocket.connected_clients}</span>
                  </div>
                  <div className="diag-item">
                    <span className="diag-label">Events Delivered</span>
                    <span className="diag-value">
                      {(diagnostics.websocket.throttler_stats?.total_delivered as number) ?? "—"}
                    </span>
                  </div>
                </div>
              </div>

              {/* Rate Limiters */}
              <div className="diagnostics-section">
                <h4>Rate Limiters</h4>
                <RateLimiterMeter
                  name="Overlay"
                  stats={diagnostics.rate_limiters.overlay}
                />
                <RateLimiterMeter
                  name="Signals"
                  stats={diagnostics.rate_limiters.signals}
                />
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

interface RateLimiterMeterProps {
  name: string;
  stats: {
    requests_per_second: number;
    total_requests: number;
    rejected_requests: number;
    rejection_rate: number;
    active_clients: number;
  };
}

function RateLimiterMeter({ name, stats }: RateLimiterMeterProps) {
  const headroom = 100 - stats.rejection_rate;

  return (
    <div className="rate-limiter-item">
      <div className="rate-limiter-header">
        <span className="rate-limiter-name">{name}</span>
        <span className="rate-limiter-rate">{stats.requests_per_second} req/s</span>
      </div>
      <div className="rate-limiter-bar">
        <div
          className={`rate-limiter-fill ${headroom < 30 ? "warning" : headroom < 70 ? "moderate" : "healthy"}`}
          style={{ width: `${headroom}%` }}
        />
      </div>
      <div className="rate-limiter-stats">
        <span>Total: {stats.total_requests}</span>
        <span>Rejected: {stats.rejected_requests}</span>
        <span>Headroom: {headroom.toFixed(1)}%</span>
      </div>
    </div>
  );
}
