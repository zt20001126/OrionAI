import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import "./toast.css";

export type ToastType = "success" | "error" | "warning" | "info";

interface ToastOptions {
  title?: string;
}

interface ToastContextValue {
  showToast: (type: ToastType, description: string, options?: ToastOptions) => void;
}

interface ToastItem {
  id: number;
  type: ToastType;
  title: string;
  description: string;
  isExiting: boolean;
}

interface ToastProviderProps {
  children: ReactNode;
}

const toastTitles: Record<ToastType, string> = {
  success: "操作成功",
  error: "操作失败",
  warning: "请注意",
  info: "提示",
};
const TOAST_ENTRY_DURATION_MS = 200;
const TOAST_VISIBLE_DURATION_MS = 2000;
const TOAST_EXIT_DURATION_MS = 300;

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: ToastProviderProps) {
  const [toast, setToast] = useState<ToastItem | null>(null);
  const nextId = useRef(0);
  const timers = useRef<{ dismiss: number | null; remove: number | null }>({
    dismiss: null,
    remove: null,
  });
  const isMounted = useRef(false);

  const clearTimers = useCallback(() => {
    if (timers.current.dismiss !== null) {
      window.clearTimeout(timers.current.dismiss);
      timers.current.dismiss = null;
    }
    if (timers.current.remove !== null) {
      window.clearTimeout(timers.current.remove);
      timers.current.remove = null;
    }
  }, []);

  useEffect(() => {
    isMounted.current = true;
    return () => {
      isMounted.current = false;
      clearTimers();
    };
  }, [clearTimers]);

  const showToast = useCallback(
    (type: ToastType, description: string, options?: ToastOptions) => {
      clearTimers();
      const id = ++nextId.current;
      setToast({
        id,
        type,
        title: options?.title ?? toastTitles[type],
        description,
        isExiting: false,
      });

      timers.current.dismiss = window.setTimeout(() => {
        if (!isMounted.current) return;
        setToast((current) => (current?.id === id ? { ...current, isExiting: true } : current));
        timers.current.dismiss = null;
        timers.current.remove = window.setTimeout(() => {
          if (isMounted.current) {
            setToast((current) => (current?.id === id ? null : current));
          }
          timers.current.remove = null;
        }, TOAST_EXIT_DURATION_MS);
      }, TOAST_ENTRY_DURATION_MS + TOAST_VISIBLE_DURATION_MS);
    },
    [clearTimers],
  );

  const value = useMemo(() => ({ showToast }), [showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      {toast && (
        <div className="toast-viewport">
          <div
            aria-atomic="true"
            className={`toast toast--${toast.type}${toast.isExiting ? " is-exiting" : ""}`}
            key={toast.id}
            role={toast.type === "error" ? "alert" : "status"}
          >
            <span aria-hidden="true" className="toast-icon">
              <ToastIcon type={toast.type} />
            </span>
            <span className="toast-copy">
              <strong className="toast-title">{toast.title}</strong>
              <span className="toast-description">{toast.description}</span>
            </span>
          </div>
        </div>
      )}
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast 必须在 ToastProvider 内使用。");
  }
  return context;
}

function ToastIcon({ type }: { type: ToastType }) {
  if (type === "error") {
    return (
      <svg viewBox="0 0 20 20" fill="none">
        <circle cx="10" cy="10" r="7" />
        <path d="M10 6.5v4.2M10 13.6h.01" />
      </svg>
    );
  }

  if (type === "success") {
    return (
      <svg viewBox="0 0 20 20" fill="none">
        <circle cx="10" cy="10" r="7" />
        <path d="m6.8 10.2 2.1 2.1 4.4-4.5" />
      </svg>
    );
  }

  if (type === "warning") {
    return (
      <svg viewBox="0 0 20 20" fill="none">
        <path d="m10 3 7.2 12.5H2.8L10 3Z" />
        <path d="M10 7.2v3.7M10 13.2h.01" />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 20 20" fill="none">
      <circle cx="10" cy="10" r="7" />
      <path d="M10 9v4M10 6.7h.01" />
    </svg>
  );
}
