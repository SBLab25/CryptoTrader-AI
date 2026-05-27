"use client";

import { useEffect } from "react";

import { useStore } from "@/store";

const toneMap = {
  default: "border-[#1e1e2e] bg-[#111118]",
  success: "border-[#00ff88]/25 bg-[#00ff88]/10",
  warning: "border-[#ffaa00]/25 bg-[#ffaa00]/10",
  error: "border-[#ff4466]/25 bg-[#ff4466]/10"
};

export function Toaster() {
  const { toasts, removeToast } = useStore((state) => ({
    toasts: state.toasts,
    removeToast: state.removeToast
  }));

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-full max-w-sm flex-col gap-2">
      {toasts.map((toast) => (
        <Toast key={toast.id} {...toast} onDismiss={removeToast} />
      ))}
    </div>
  );
}

function Toast({
  id,
  title,
  description,
  variant,
  onDismiss
}: {
  id: string;
  title: string;
  description?: string;
  variant: "default" | "success" | "warning" | "error";
  onDismiss: (id: string) => void;
}) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(id), 4000);
    return () => clearTimeout(timer);
  }, [id, onDismiss]);

  return (
    <div
      className={`pointer-events-auto animate-fade-up rounded-xl border p-4 shadow-2xl ${toneMap[variant]}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-white">{title}</div>
          {description ? <div className="mt-1 text-xs text-slate-400">{description}</div> : null}
        </div>
        <button className="text-slate-500 hover:text-white" onClick={() => onDismiss(id)} type="button">
          x
        </button>
      </div>
    </div>
  );
}
