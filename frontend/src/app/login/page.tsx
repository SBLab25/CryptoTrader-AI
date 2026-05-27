"use client";

import { FormEvent, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { auth } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const params = useSearchParams();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await auth.login(username, password);
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail ?? "Login failed");
      }
      router.replace(params.get("from") || "/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-6 py-12">
      <div className="w-full max-w-md rounded-2xl border border-[#1e1e2e] bg-[#0d0d14]/95 p-8 shadow-2xl">
        <div className="mb-8">
          <div className="text-[#00ff88] text-xs font-mono uppercase tracking-[0.24em]">Phase 7</div>
          <h1 className="mt-3 text-3xl font-semibold text-white">CryptoTraderAI v2</h1>
          <p className="mt-2 text-sm text-slate-400">
            Sign in to the trading dashboard and live control surface.
          </p>
        </div>

        <form className="space-y-5" onSubmit={handleSubmit}>
          <label className="block">
            <span className="mb-1.5 block text-[11px] font-mono uppercase tracking-[0.2em] text-slate-500">
              Username
            </span>
            <input
              className="w-full rounded-xl border border-[#1e1e2e] bg-[#09090d] px-4 py-3 text-white outline-none transition focus:border-[#00ff88]"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
            />
          </label>

          <label className="block">
            <span className="mb-1.5 block text-[11px] font-mono uppercase tracking-[0.2em] text-slate-500">
              Password
            </span>
            <input
              className="w-full rounded-xl border border-[#1e1e2e] bg-[#09090d] px-4 py-3 text-white outline-none transition focus:border-[#00ff88]"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
            />
          </label>

          {error ? (
            <div className="rounded-xl border border-[#ff4466]/30 bg-[#ff4466]/10 px-4 py-3 text-sm text-[#ff7f99]">
              {error}
            </div>
          ) : null}

          <button
            disabled={busy}
            className="w-full rounded-xl bg-[#00ff88] px-4 py-3 text-sm font-semibold text-[#07120d] transition hover:bg-[#00e07a] disabled:cursor-not-allowed disabled:opacity-60"
            type="submit"
          >
            {busy ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
