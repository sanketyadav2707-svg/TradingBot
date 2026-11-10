"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Shield, ShieldAlert } from "lucide-react";
import { tradingBotApi } from "@/lib/api/client";
import type { RiskSnapshotResponse } from "@/lib/api/types";

export function PaperRiskPanel() {
  const [risk, setRisk] = useState<RiskSnapshotResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    let controller: AbortController | null = null;
    let busy = false;
    const refresh = async () => {
      if (busy) return;
      busy = true;
      controller = new AbortController();
      try {
        const data = await tradingBotApi.risk(controller.signal);
        if (!disposed) {
          setRisk(data);
          setError(null);
        }
      } catch (reason) {
        if (!disposed && !(reason instanceof Error && reason.name === "AbortError")) {
          setError(reason instanceof Error ? reason.message : "Risk state unavailable.");
        }
      } finally {
        busy = false;
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 15_000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
      controller?.abort();
    };
  }, []);

  return (
    <section className="rounded-xl border border-[#263241] bg-[#0e151e]">
      <div className="flex items-center justify-between border-b border-[#202b38] px-3.5 py-3">
        <div>
          <h2 className="text-[11px] font-semibold text-slate-200">Risk & execution guardrails</h2>
          <p className="mt-0.5 text-[8px] text-slate-500">PERSISTED ACCOUNT SNAPSHOT · NO ORDER CONTROL</p>
        </div>
        <ShieldAlert size={14} className="text-amber-300"/>
      </div>
      <div className="space-y-3 p-3">
        <div className="flex items-center justify-between rounded-lg border border-amber-400/15 bg-amber-400/[.04] px-3 py-2">
          <span className="text-[9px] text-slate-400">Server risk gate</span>
          <span className="font-mono text-[10px] font-bold text-amber-300">{risk?.gate ?? "UNKNOWN"}</span>
        </div>
        <div className="flex items-center justify-between border-b border-[#202b38]/70 pb-2 text-[9px]">
          <span className="text-slate-500">Daily loss used</span>
          <span className="font-mono text-slate-300">{risk?.daily_loss_used ? `$${risk.daily_loss_used.amount}` : "Unavailable"}</span>
        </div>
        <div className="flex items-center justify-between border-b border-[#202b38]/70 pb-2 text-[9px]">
          <span className="text-slate-500">Configured daily cap</span>
          <span className="font-mono text-slate-300">{risk?.daily_loss_limit ? `$${risk.daily_loss_limit.amount}` : "Unavailable"}</span>
        </div>
        <div className="flex items-center justify-between border-b border-[#202b38]/70 pb-2 text-[9px]">
          <span className="text-slate-500">Open positions</span>
          <span className="font-mono text-slate-300">{risk?.open_positions ?? "Unavailable"}</span>
        </div>
        <div className="flex items-center justify-between text-[9px]">
          <span className="text-slate-500">Max contracts per risk config</span>
          <span className="font-mono text-slate-300">{risk?.max_contracts ?? "Unavailable"}</span>
        </div>
        <div className="flex items-start gap-1.5 rounded border border-amber-400/15 bg-amber-400/[.04] p-2 text-[8px] leading-relaxed text-amber-200/80">
          <AlertTriangle size={11} className="mt-0.5 shrink-0"/>
          Risk gate remains UNKNOWN until an active strategy session supplies a current account evaluation. Configured limits are research defaults, not enforced prop-firm rules.
        </div>
        {error && <div className="text-[8px] text-rose-300">{error}</div>}
        <div className="flex items-center gap-1.5 text-[8px] text-slate-500"><Shield size={10}/> No live execution or risk mutation endpoint exists.</div>
      </div>
    </section>
  );
}
