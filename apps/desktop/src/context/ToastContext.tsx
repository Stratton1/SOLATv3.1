/**
 * Global toast notification system with history.
 *
 * Usage:
 *   const { showToast, notifications, clearHistory } = useToast();
 *   showToast("Copied 42 rows", "success");
 */

import {
  createContext,
  useContext,
  useCallback,
  useState,
  type ReactNode,
} from "react";

// =============================================================================
// Types
// =============================================================================

export type ToastType = "info" | "success" | "error" | "warning";

export interface Toast {
  id: number;
  title?: string;
  message: string;
  type: ToastType;
  timestamp: number;
  duration?: number;
}

interface ToastContextValue {
  showToast: (message: string, type?: ToastType, title?: string, duration?: number) => void;
  dismissToast: (id: number) => void;
  notifications: Toast[]; // History of all notifications
  clearHistory: () => void;
}

// =============================================================================
// Context
// =============================================================================

const ToastContext = createContext<ToastContextValue | null>(null);

let nextId = 0;
const DEFAULT_DURATION = 4000;
const MAX_TOASTS_VISIBLE = 5;
const MAX_HISTORY = 50;

// =============================================================================
// Provider
// =============================================================================

export function ToastProvider({ children }: { children: ReactNode }) {
  const [activeToasts, setActiveToasts] = useState<Toast[]>([]);
  const [history, setHistory] = useState<Toast[]>([]);

  const showToast = useCallback(
    (message: string, type: ToastType = "info", title?: string, duration = DEFAULT_DURATION) => {
      const id = ++nextId;
      const newToast: Toast = {
        id,
        title,
        message,
        type,
        timestamp: Date.now(),
        duration,
      };

      // Add to active toasts (limit to MAX_TOASTS_VISIBLE)
      setActiveToasts((prev) => {
        const updated = [...prev, newToast];
        if (updated.length > MAX_TOASTS_VISIBLE) {
          return updated.slice(updated.length - MAX_TOASTS_VISIBLE);
        }
        return updated;
      });

      // Add to history
      setHistory((prev) => [newToast, ...prev].slice(0, MAX_HISTORY));

      // Auto-dismiss active toast
      if (duration > 0) {
        setTimeout(() => {
          setActiveToasts((prev) => prev.filter((t) => t.id !== id));
        }, duration);
      }
    },
    []
  );

  const dismissToast = useCallback((id: number) => {
    setActiveToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const clearHistory = useCallback(() => {
    setHistory([]);
  }, []);

  return (
    <ToastContext.Provider value={{ showToast, dismissToast, notifications: history, clearHistory }}>
      {children}
      {/* Toast container — portalled to bottom-right */}
      <div className="toast-container">
        {activeToasts.map((toast) => (
          <div
            key={toast.id}
            className={`toast-item toast-${toast.type}`}
            onClick={() => dismissToast(toast.id)}
          >
            <div className="toast-icon">
              {toast.type === "success" && "\u2713"}
              {toast.type === "error" && "\u2717"}
              {toast.type === "warning" && "\u26A0"}
              {toast.type === "info" && "\u2139"}
            </div>
            <div className="toast-content">
              {toast.title && <div className="toast-title">{toast.title}</div>}
              <div className="toast-message">{toast.message}</div>
            </div>
            <div className="toast-close">×</div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

// =============================================================================
// Hook
// =============================================================================

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return ctx;
}
