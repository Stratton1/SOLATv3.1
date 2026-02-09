/**
 * LIVE Trading Banner - Displayed when trading in LIVE mode.
 *
 * This banner is intentionally prominent and hard to ignore.
 * It serves as a constant reminder that real money is at risk.
 */

import { useLiveGates } from "../hooks/useLiveGates";

interface LiveBannerProps {
  onRevoke?: () => void;
}

export function LiveBanner({ onRevoke }: LiveBannerProps) {
  const { isLiveMode, gates, revokeLive, loading } = useLiveGates(true, 5000);

  if (!isLiveMode) return null;

  const handleRevoke = async () => {
    await revokeLive();
    onRevoke?.();
  };

  const remainingTime = gates?.details.ui_confirmation_age_s
    ? Math.max(0, (gates?.details.ui_confirmation_age_s as number) || 0)
    : null;

  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-red-600 text-white py-1 px-4 flex items-center justify-between shadow-lg">
      <div className="flex items-center gap-3">
        <div className="w-3 h-3 rounded-full bg-white animate-pulse" />
        <span className="font-bold tracking-wider">LIVE TRADING ACTIVE</span>
        <span className="text-red-200 text-sm">
          Real money at risk
        </span>
      </div>

      <div className="flex items-center gap-4">
        {remainingTime !== null && (
          <span className="text-red-200 text-sm">
            Confirmation expires in {Math.round((600 - remainingTime) / 60)}m
          </span>
        )}
        <button
          onClick={handleRevoke}
          disabled={loading}
          className="px-3 py-1 bg-red-800 hover:bg-red-700 rounded text-sm font-medium"
        >
          {loading ? "..." : "Revoke LIVE"}
        </button>
      </div>
    </div>
  );
}

/**
 * LIVE Watermark - Subtle background watermark for terminal/chart areas.
 */
export function LiveWatermark() {
  const { isLiveMode } = useLiveGates();

  if (!isLiveMode) return null;

  return (
    <div className="absolute inset-0 pointer-events-none overflow-hidden z-0">
      <div
        className="absolute inset-0 flex items-center justify-center opacity-5"
        style={{
          transform: "rotate(-30deg) scale(2)",
        }}
      >
        <span className="text-red-500 font-bold text-9xl tracking-widest">
          LIVE
        </span>
      </div>
    </div>
  );
}

/**
 * LIVE Mode Indicator - Small indicator for headers/status bars.
 */
export function LiveModeIndicator() {
  const { isLiveMode, isLiveAllowed, blockers } = useLiveGates();

  if (isLiveMode) {
    return (
      <div className="flex items-center gap-2 px-2 py-1 bg-red-600 rounded text-white text-sm font-bold">
        <div className="w-2 h-2 rounded-full bg-white animate-pulse" />
        LIVE
      </div>
    );
  }

  if (isLiveAllowed) {
    return (
      <div className="flex items-center gap-2 px-2 py-1 bg-yellow-600 rounded text-white text-sm">
        <div className="w-2 h-2 rounded-full bg-white" />
        LIVE Ready
      </div>
    );
  }

  return (
    <div
      className="flex items-center gap-2 px-2 py-1 bg-zinc-700 rounded text-zinc-300 text-sm cursor-help"
      title={`LIVE blocked: ${blockers.slice(0, 3).join(", ")}`}
    >
      <div className="w-2 h-2 rounded-full bg-zinc-500" />
      DEMO
    </div>
  );
}

export default LiveBanner;
