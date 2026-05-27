"use client";

import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";

import { frontendTransforms } from "@/lib/api";
import type {
  ApprovalRequest,
  Portfolio,
  Position,
  RiskStatus,
  Signal,
  SystemStatus,
  TrainingStatus,
  WSEvent
} from "@/types";

interface Toast {
  id: string;
  title: string;
  description?: string;
  variant: "default" | "success" | "warning" | "error";
}

interface AppState {
  status: SystemStatus | null;
  connected: boolean;
  portfolio: Portfolio | null;
  positions: Position[];
  signals: Signal[];
  approvals: ApprovalRequest[];
  riskStatus: RiskStatus | null;
  trainingStatus: TrainingStatus | null;
  toasts: Toast[];
  setStatus: (value: SystemStatus) => void;
  setConnected: (value: boolean) => void;
  setPortfolio: (value: Portfolio) => void;
  setPositions: (value: Position[]) => void;
  addSignal: (value: Signal) => void;
  setApprovals: (value: ApprovalRequest[]) => void;
  updateApproval: (id: string, status: ApprovalRequest["status"]) => void;
  setRiskStatus: (value: RiskStatus) => void;
  setTrainingStatus: (value: TrainingStatus) => void;
  addToast: (value: Omit<Toast, "id">) => void;
  removeToast: (id: string) => void;
}

export const useStore = create<AppState>()(
  subscribeWithSelector((set) => ({
    status: null,
    connected: false,
    portfolio: null,
    positions: [],
    signals: [],
    approvals: [],
    riskStatus: null,
    trainingStatus: null,
    toasts: [],
    setStatus: (status) => set({ status }),
    setConnected: (connected) => set({ connected }),
    setPortfolio: (portfolio) => set({ portfolio }),
    setPositions: (positions) => set({ positions }),
    addSignal: (signal) => set((state) => ({ signals: [signal, ...state.signals].slice(0, 100) })),
    setApprovals: (approvals) => set({ approvals }),
    updateApproval: (id, status) =>
      set((state) => ({
        approvals: state.approvals.map((item) => (item.id === id ? { ...item, status } : item))
      })),
    setRiskStatus: (riskStatus) => set({ riskStatus }),
    setTrainingStatus: (trainingStatus) => set({ trainingStatus }),
    addToast: (toast) =>
      set((state) => ({
        toasts: [...state.toasts, { ...toast, id: crypto.randomUUID() }]
      })),
    removeToast: (id) =>
      set((state) => ({
        toasts: state.toasts.filter((toast) => toast.id !== id)
      }))
  }))
);

let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let currentToken = "";

function websocketBase() {
  const rawBase = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
  const url = new URL(rawBase);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/ws";
  url.search = "";
  return url.toString().replace(/\/$/, "");
}

export function connectWS(token: string) {
  currentToken = token;
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  ws = new WebSocket(`${websocketBase()}?token=${encodeURIComponent(token)}`);

  ws.onopen = () => {
    useStore.getState().setConnected(true);
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  };

  ws.onclose = () => {
    useStore.getState().setConnected(false);
    reconnectTimer = setTimeout(() => {
      if (currentToken) {
        connectWS(currentToken);
      }
    }, 3000);
  };

  ws.onerror = () => {
    ws?.close();
  };

  ws.onmessage = (event) => {
    try {
      const payload: WSEvent = JSON.parse(event.data);
      const store = useStore.getState();
      switch (payload.type) {
        case "init":
          store.setStatus(payload.data.status);
          if (store.portfolio) {
            store.setPortfolio({
              ...store.portfolio,
              total_value: payload.data.portfolio?.total_value ?? store.portfolio.total_value,
              unrealized_pnl: payload.data.portfolio?.total_pnl ?? store.portfolio.unrealized_pnl,
              available_balance: payload.data.portfolio?.available_balance ?? store.portfolio.available_balance,
              invested_value: payload.data.portfolio?.invested_value ?? store.portfolio.invested_value,
              total_pnl_pct: payload.data.portfolio?.total_pnl_pct ?? store.portfolio.total_pnl_pct
            });
          }
          break;
        case "signal":
          store.addSignal(frontendTransforms.normalizeSignal(payload.data));
          break;
        case "portfolio":
          if (store.portfolio) {
            store.setPortfolio({
              ...store.portfolio,
              total_value: payload.data.total_value ?? store.portfolio.total_value,
              unrealized_pnl: payload.data.total_pnl ?? store.portfolio.unrealized_pnl,
              available_balance: payload.data.available_balance ?? store.portfolio.available_balance,
              invested_value: payload.data.invested_value ?? store.portfolio.invested_value,
              total_pnl_pct: payload.data.total_pnl_pct ?? store.portfolio.total_pnl_pct
            });
          }
          break;
        case "trade":
          store.addToast({
            title: `${payload.data.symbol} trade update`,
            description: payload.data.status,
            variant: "default"
          });
          break;
        case "approval":
        case "approval_decided":
          store.addToast({
            title: payload.type === "approval" ? "Approval required" : "Approval updated",
            description: payload.data.symbol ?? payload.data.id,
            variant: "warning"
          });
          break;
        case "risk":
          store.setRiskStatus(payload.data);
          break;
        case "training":
          store.setTrainingStatus(payload.data);
          break;
        default:
          break;
      }
    } catch {
      // Ignore malformed events
    }
  };
}

export function disconnectWS() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (ws) {
    ws.close();
    ws = null;
  }
}
