"use client";

import { useEffect } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Keep diagnostics in the browser console; never expose stack traces in the UI.
    console.error("TradingBot dashboard route failed", error);
  }, [error]);

  return (
    <main className="flex min-h-[70vh] items-center justify-center px-4 py-12">
      <section
        role="alert"
        className="w-full max-w-lg rounded-2xl border border-rose-400/20 bg-[#0e151e] p-6 shadow-2xl shadow-black/20"
      >
        <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-rose-400/20 bg-rose-400/10 text-rose-300">
          <AlertTriangle size={19} />
        </div>
        <p className="mt-5 text-[10px] font-bold tracking-[.18em] text-rose-300">
          DASHBOARD COMPONENT ERROR
        </p>
        <h1 className="mt-2 text-lg font-semibold text-slate-100">
          This view could not be rendered
        </h1>
        <p className="mt-2 text-sm leading-6 text-slate-400">
          The dashboard stopped rendering this section. Your persisted paper-account
          records are not changed by this display error. Check the local API and
          browser console before continuing.
        </p>
        {error.digest && (
          <p className="mt-3 font-mono text-[10px] text-slate-600">
            Diagnostic ID: {error.digest}
          </p>
        )}
        <button
          type="button"
          onClick={() => reset()}
          className="mt-6 inline-flex items-center gap-2 rounded-lg border border-cyan-300/30 bg-cyan-300 px-4 py-2.5 text-xs font-semibold text-slate-950 hover:bg-cyan-200"
        >
          <RefreshCw size={13} />
          Retry dashboard
        </button>
        <p className="mt-4 text-[10px] leading-5 text-amber-300/80">
          Paper-only mode remains in force. A successful retry does not indicate
          that market data or broker connectivity is available.
        </p>
      </section>
    </main>
  );
}
