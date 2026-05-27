"use client";

import { useState } from "react";
import useSWR from "swr";

import { training } from "@/lib/api";
import { formatPct } from "@/lib/format";
import { useStore } from "@/store";

const SYMBOLS = ["BTC_USDT", "ETH_USDT", "SOL_USDT"];
const SPEEDS = [1, 10, 50, 100, 500];

export default function TrainingPage() {
  const { status, trainingStatus, setTrainingStatus, addToast } = useStore((state) => ({
    status: state.status,
    trainingStatus: state.trainingStatus,
    setTrainingStatus: state.setTrainingStatus,
    addToast: state.addToast
  }));

  const [symbol, setSymbol] = useState("BTC_USDT");
  const [timesteps, setTimesteps] = useState(500000);
  const [speed, setSpeed] = useState(100);
  const [busy, setBusy] = useState(false);

  const { data: checkpoints, mutate } = useSWR("training-checkpoints", training.checkpoints, {
    refreshInterval: 10000
  });

  async function handleStart() {
    setBusy(true);
    try {
      await training.start(symbol, timesteps, speed);
      const next = await training.status();
      setTrainingStatus(next);
      addToast({ title: "Training started", description: `${symbol} for ${timesteps.toLocaleString()} steps`, variant: "success" });
    } catch (err) {
      addToast({ title: "Could not start training", description: err instanceof Error ? err.message : "Unknown error", variant: "error" });
    } finally {
      setBusy(false);
    }
  }

  async function handleStop() {
    setBusy(true);
    try {
      await training.stop();
      const next = await training.status();
      setTrainingStatus(next);
      addToast({ title: "Training stopped", variant: "warning" });
    } finally {
      setBusy(false);
    }
  }

  async function handleLoad(path: string) {
    try {
      await training.loadModel(path);
      setTrainingStatus(await training.status());
      await mutate();
      addToast({ title: "Checkpoint loaded", description: path, variant: "success" });
    } catch (err) {
      addToast({ title: "Load failed", description: err instanceof Error ? err.message : "Unknown error", variant: "error" });
    }
  }

  const running = trainingStatus?.running ?? false;
  const progress = trainingStatus ? trainingStatus.episode / Math.max(trainingStatus.total_episodes, 1) : 0;
  const isDemo = status?.mode === "demo";

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold text-white">Training mode</h1>
        <p className="mt-1 text-sm text-slate-500">Replay and reinforcement-learning control room.</p>
      </div>

      {!isDemo ? (
        <div className="rounded-xl border border-[#ffaa00]/30 bg-[#ffaa00]/10 p-4 text-sm text-[#ffd580]">
          Training works best with <code>TRADING_MODE=demo</code>. Current mode: {status?.mode ?? "unknown"}.
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-3">
        <section className="space-y-5 rounded-xl border border-[#1e1e2e] bg-[#111118] p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Configuration</div>
          <Field label="Symbol">
            <select
              className="w-full rounded-xl border border-[#1e1e2e] bg-[#0d0d14] px-3 py-2 text-white"
              disabled={running}
              onChange={(event) => setSymbol(event.target.value)}
              value={symbol}
            >
              {SYMBOLS.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </Field>
          <Field label={`Timesteps: ${(timesteps / 1000).toFixed(0)}k`}>
            <input
              className="w-full accent-[#00ff88]"
              disabled={running}
              max={2000000}
              min={100000}
              onChange={(event) => setTimesteps(Number(event.target.value))}
              step={100000}
              type="range"
              value={timesteps}
            />
          </Field>
          <Field label="Replay speed">
            <div className="flex flex-wrap gap-2">
              {SPEEDS.map((item) => (
                <button
                  key={item}
                  className={`rounded-lg border px-3 py-1.5 text-xs ${
                    item === speed ? "border-[#00ff88]/30 bg-[#00ff88]/10 text-[#00ff88]" : "border-[#1e1e2e] bg-[#0d0d14] text-slate-400"
                  }`}
                  disabled={running}
                  onClick={() => setSpeed(item)}
                  type="button"
                >
                  {item}x
                </button>
              ))}
            </div>
          </Field>
          <button
            className={`w-full rounded-xl px-4 py-3 text-sm font-semibold ${
              running ? "border border-[#ff4466]/30 bg-[#ff4466]/10 text-[#ff7f99]" : "bg-[#00ff88] text-[#07120d]"
            }`}
            disabled={busy || (!isDemo && !running)}
            onClick={running ? handleStop : handleStart}
            type="button"
          >
            {busy ? "Working..." : running ? "Stop training" : "Start training"}
          </button>
        </section>

        <section className="rounded-xl border border-[#1e1e2e] bg-[#111118] p-5">
          <div className="mb-4 flex items-center justify-between">
            <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Progress</div>
            {running ? <span className="text-xs text-[#00ff88]">Running</span> : null}
          </div>
          {trainingStatus ? (
            <div className="space-y-4">
              <div>
                <div className="mb-2 flex items-center justify-between text-xs text-slate-500">
                  <span>Episode {trainingStatus.episode}</span>
                  <span>{(progress * 100).toFixed(1)}%</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-[#1e1e2e]">
                  <div className="h-full bg-[#00ff88]" style={{ width: `${progress * 100}%` }} />
                </div>
              </div>
              <Metric label="Sharpe ratio" value={trainingStatus.sharpe_ratio.toFixed(3)} />
              <Metric label="Win rate" value={formatPct(trainingStatus.win_rate)} />
              <Metric label="Average reward" value={trainingStatus.avg_reward.toFixed(4)} />
              <Metric label="Best reward" value={trainingStatus.best_reward.toFixed(4)} />
            </div>
          ) : (
            <div className="py-12 text-center text-sm text-slate-600">No training session running</div>
          )}
        </section>

        <section className="rounded-xl border border-[#1e1e2e] bg-[#111118] p-5">
          <div className="mb-4 text-[11px] uppercase tracking-[0.18em] text-slate-500">Checkpoints</div>
          {!checkpoints?.length ? (
            <div className="py-12 text-center text-sm text-slate-600">No checkpoints found</div>
          ) : (
            <div className="space-y-2">
              {checkpoints.map((checkpoint) => (
                <div key={checkpoint.path} className="flex items-center justify-between rounded-xl border border-[#1e1e2e] bg-[#0d0d14] px-3 py-2">
                  <div>
                    <div className="text-sm text-white">{checkpoint.name}</div>
                    <div className="text-[11px] text-slate-500">{new Date(checkpoint.created_at).toLocaleString()}</div>
                  </div>
                  <button className="text-xs text-[#4488ff]" onClick={() => handleLoad(checkpoint.path)} type="button">
                    Load
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-2 text-[11px] uppercase tracking-[0.18em] text-slate-500">{label}</div>
      {children}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[#1e1e2e] bg-[#0d0d14] p-3">
      <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">{label}</div>
      <div className="mt-1 font-mono text-lg text-white">{value}</div>
    </div>
  );
}
