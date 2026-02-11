/**
 * Global toast notification system.
 *
 * Usage:
 *   const { showToast } = useToast();
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

interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

interface ToastContextValue {
  showToast: (message: string, type?: ToastType) => void;
}

// =============================================================================
// Context
// =============================================================================

const ToastContext = createContext<ToastContextValue | null>(null);

let nextId = 0;
const TOAST_DURATION_MS = 3000;
const MAX_TOASTS = 5;

// =============================================================================
// Provider
// =============================================================================

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const showToast = useCallback((message: string, type: ToastType = "info") => {
    const id = ++nextId;
    setToasts((prev) => [...prev.slice(-(MAX_TOASTS - 1)), { id, message, type }]);

    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, TOAST_DURATION_MS);
  }, []);

  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      {/* Toast container — portalled to bottom-right */}
      {toasts.length > 0 && (
        <div className="toast-container">
          {toasts.map((toast) => (
            <div
              key={toast.id}
              className={`toast-item toast-${toast.type}`}
              onClick={() => dismissToast(toast.id)}
            >
              <span className="toast-icon">
                {toast.type === "success" && "\u2713"}
                {toast.type === "error" && "\u2717"}
                {toast.type === "warning" && "\u26A0"}
                {toast.type === "info" && "\u2139"}
              </span>
              <span className="toast-message">{toast.message}</span>
            </div>
          ))}
        </div>
      )}
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
