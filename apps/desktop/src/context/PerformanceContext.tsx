/**
 * Performance mode context for UI optimization.
 *
 * When Performance Mode is ON:
 * - Animations are disabled
 * - WS tick rate is reduced to 2/s
 * - Expensive renders are throttled
 */

import { createContext, useContext, useState, useCallback, ReactNode } from "react";

interface PerformanceSettings {
  /** Performance mode toggle */
  performanceMode: boolean;

  /** Reduce animations when true */
  reduceAnimations: boolean;

  /** Maximum WS updates per second (2 in perf mode, 10 normally) */
  maxWsUpdatesPerSecond: number;

  /** Debounce delay for overlay requests (ms) */
  overlayDebounceMs: number;

  /** Maximum table rows before virtualization kicks in */
  maxTableRows: number;
}

interface PerformanceContextValue extends PerformanceSettings {
  togglePerformanceMode: () => void;
  setPerformanceMode: (enabled: boolean) => void;
}

const defaultSettings: PerformanceSettings = {
  performanceMode: false,
  reduceAnimations: false,
  maxWsUpdatesPerSecond: 10,
  overlayDebounceMs: 250,
  maxTableRows: 500,
};

const perfModeSettings: PerformanceSettings = {
  performanceMode: true,
  reduceAnimations: true,
  maxWsUpdatesPerSecond: 2,
  overlayDebounceMs: 500, // Longer debounce in perf mode
  maxTableRows: 200, // Fewer rows in perf mode
};

const PerformanceContext = createContext<PerformanceContextValue | undefined>(
  undefined
);

export function PerformanceProvider({ children }: { children: ReactNode }) {
  const [performanceMode, setPerformanceModeState] = useState(() => {
    // Load from localStorage
    const stored = localStorage.getItem("performanceMode");
    return stored === "true";
  });

  const settings = performanceMode ? perfModeSettings : defaultSettings;

  const setPerformanceMode = useCallback((enabled: boolean) => {
    setPerformanceModeState(enabled);
    localStorage.setItem("performanceMode", String(enabled));
  }, []);

  const togglePerformanceMode = useCallback(() => {
    setPerformanceMode(!performanceMode);
  }, [performanceMode, setPerformanceMode]);

  return (
    <PerformanceContext.Provider
      value={{
        ...settings,
        performanceMode,
        togglePerformanceMode,
        setPerformanceMode,
      }}
    >
      {children}
    </PerformanceContext.Provider>
  );
}

export function usePerformance(): PerformanceContextValue {
  const context = useContext(PerformanceContext);
  if (context === undefined) {
    throw new Error("usePerformance must be used within a PerformanceProvider");
  }
  return context;
}

/**
 * Hook for using throttled WS updates based on performance mode.
 */
export function useWsThrottle() {
  const { maxWsUpdatesPerSecond } = usePerformance();
  const intervalMs = 1000 / maxWsUpdatesPerSecond;
  return intervalMs;
}
