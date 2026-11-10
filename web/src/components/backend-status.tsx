"use client";

import { useEffect, useState } from "react";
import { Activity, AlertTriangle, CheckCircle2, CircleHelp, Database, RefreshCw, Shield } from "lucide-react";
import { tradingBotApi } from "@/lib/api/client";
import type {
  DashboardSummaryResponse,
  HealthResponse,
  InstrumentsResponse,
  RiskSnapshotResponse,
} from "@/lib/api/types";

function StateDot({ tone }: { tone: "green" | "amber" | "red" | "slate" }) {
  const color = {
    green: "bg-emerald-400",
    amber: "bg-amber-400",
    red: "bg-rose-400",
    slate: "bg-slate-500",
  }[tone];
  return <span aria-hidden="true" className={`inline-block h-1.5 w-1.5 rounded-full ${color}`} />;
}

function Stat({
  label,
  value,
  detail,
  tone = "slate",
}: {
  label: string;
  value: string;
  detail: string;
  tone?: "green" | "amber" | "red" | "slate";
}) {
  const color = {
    green: "text-emerald-300",
    amber: "text-amber-300",
    red: "text-rose-300",
    slate: "text-slate-200",
  }[tone];
  return (
    <div className="min-w-0 rounded-lg border border-[#202b38] bg-[#0a1119] p-3">
      <div className="text-[8px] font-bold tracking-[.14em] text-slate-500">{label}</div>
      <div className={`mt-2 truncate font-mono text-[13px] font-semibold ${color}`}>{value}</div>
      <div className="mt-1 truncate text-[8px] text-slate-500" title={detail}>{detail}</div>
    </div>
  );
}

export function BackendStatusPanel() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [summary, setSummary] = useState<DashboardSummaryResponse | null>(null);
  const [instruments, setInstruments] = useState<InstrumentsResponse | null>(null);
  const [risk, setRisk] = useState<RiskSnapshotResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastChecked, setLastChecked] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    let refreshing = false;
    let controller: AbortController | null = null;

    const refresh = async () => {
      if (refreshing) return;
      refreshing = true;
      controller = new AbortController();
      const signal = controller.signal;
      const [healthResult, summaryResult, instrumentResult, riskResult] = await Promise.allSettled([
        tradingBotApi.health(signal),
        tradingBotApi.summary(signal),
        tradingBotApi.instruments(signal),
        tradingBotApi.risk(signal),
      ]);

      if (!disposed) {
        const healthy = healthResult.status === "fulfilled" ? healthResult.value : null;
        setHealth(healthy);
        setSummary(summaryResult.status === "fulfilled" ? summaryResult.value : null);
        setInstruments(instrumentResult.status === "fulfilled" ? instrumentResult.value : null);
        setRisk(riskResult.status === "fulfilled" ? riskResult.value : null);
        setError(
          healthy
            ? null
            : healthResult.status === "rejected" && healthResult.reason instanceof Error
              ? healthResult.reason.message
              : "The local Python API is not reachable.",
        );
        setLastChecked(new Date().toISOString());
        setLoading(false);
      }
      refreshing = false;
    };

    void refresh();
    const timer = window.setInterval(() => void refresh(), 15_000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
      controller?.abort();
    };
  }, []);

  const online = health !== null && health.status !== "error";
  const healthTone = health?.status === "ok" ? "green" : health ? "amber" : loading ? "slate" : "red";
  const runtimeMode = summary?.meta.environment ?? "UNKNOWN";
  const riskGate = risk?.gate ?? "UNKNOWN";
  const symbols = instruments?.availability === "AVAILABLE"
    ? instruments.items.map((item) => item.symbol)
    : [];

  return (
    <section className="rounded-xl border border-[#263241] bg-[#0e151e] p-3.5 sm:p-4" aria-live="polite">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-cyan-400/10 text-cyan-300">
            <Activity size={14} />
          </div>
          <div>
            <h2 className="text-[11px] font-semibold text-slate-100">Python service bridge</h2>
            <p className="mt-0.5 text-[8px] tracking-wider text-slate-500">LOCAL API · READ-ONLY · AUTO-REFRESH 15S</p>
          </div>
        </div>
        <div className={`flex items-center gap-1.5 rounded-md border px-2 py-1 text-[8px] font-bold tracking-wider ${
          healthTone === "green"
            ? "border-emerald-400/20 bg-emerald-400/[.06] text-emerald-300"
            : healthTone === "amber"
              ? "border-amber-400/20 bg-amber-400/[.06] text-amber-300"
              : healthTone === "slate"
                ? "border-slate-700 bg-slate-800/60 text-slate-300"
                : "border-rose-400/20 bg-rose-400/[.06] text-rose-300"
        }`}>
          <StateDot tone={healthTone} />
          {health?.status === "ok" ? "API ONLINE" : health?.status === "degraded" ? "API DEGRADED" : loading ? "CONNECTING" : "API OFFLINE"}
        </div>
      </div>

      {error && (
        <div className="mb-3 flex items-start gap-2 rounded-lg border border-amber-400/15 bg-amber-400/[.04] px-3 py-2">
          <AlertTriangle size={12} className="mt-0.5 shrink-0 text-amber-300" />
          <div className="min-w-0">
            <div className="text-[9px] font-semibold text-amber-200">Backend not connected</div>
            <p className="mt-1 break-words text-[8px] leading-relaxed text-amber-100/60">{error}</p>
            <p className="mt-1 text-[8px] text-slate-500">Start it with <code className="text-slate-300">tradingbot-api</code> in a separate terminal.</p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 xl:grid-cols-4">
        <Stat
          label="SERVICE HEALTH"
          value={health?.status.toUpperCase() ?? (loading ? "CHECKING" : "UNAVAILABLE")}
          detail={health ? `API v${health.version}` : "No response from localhost:8000"}
          tone={healthTone}
        />
        <Stat
          label="TRADING RUNTIME"
          value={runtimeMode}
          detail={runtimeMode === "PAPER" ? "Paper broker attached" : "No broker session attached"}
          tone={runtimeMode === "PAPER" ? "green" : "amber"}
        />
        <Stat
          label="RISK GATE"
          value={riskGate}
          detail={risk?.daily_loss_limit ? `Research default: USD ${risk.daily_loss_limit.amount} · not enforced` : "No evaluated account snapshot"}
          tone={riskGate === "PASS" ? "green" : riskGate === "BLOCK" ? "red" : "amber"}
        />
        <Stat
          label="CONFIGURED CONTRACTS"
          value={instruments?.availability === "AVAILABLE" ? String(instruments.items.length) : "UNAVAILABLE"}
          detail={symbols.length ? symbols.join(" · ") : instruments?.reason ?? "Waiting for configuration"}
          tone={symbols.length ? "green" : "slate"}
        />
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-[#202b38] pt-2 text-[8px] text-slate-500">
        <span className="flex items-center gap-1.5">
          <Database size={10} />
          Config metadata is real; market ticker, depth and prints remain synthetic demo fixtures.
        </span>
        <span className="flex items-center gap-1.5">
          {riskGate === "UNKNOWN" ? <CircleHelp size={10} /> : <Shield size={10} />}
          {riskGate === "UNKNOWN" ? "No active account risk evaluation" : "Server-reported risk gate"}
        </span>
        <span className="flex items-center gap-1.5">
          <RefreshCw size={9} />
          {lastChecked ? `Checked ${new Date(lastChecked).toLocaleTimeString()}` : "Waiting for first check"}
          {online && <CheckCircle2 size={10} className="text-emerald-400" />}
        </span>
      </div>
    </section>
  );
}
