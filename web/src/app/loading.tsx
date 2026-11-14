export default function DashboardLoading() {
  return (
    <main
      aria-label="Loading TradingBot dashboard"
      aria-busy="true"
      className="mx-auto min-h-[70vh] max-w-[1800px] space-y-4 p-3 sm:p-5"
    >
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <div className="h-5 w-40 animate-pulse rounded bg-slate-800" />
          <div className="h-3 w-64 animate-pulse rounded bg-slate-900" />
        </div>
        <div className="h-7 w-24 animate-pulse rounded bg-slate-800" />
      </div>
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => (
          <div key={index} className="h-24 animate-pulse rounded-xl border border-[#263241] bg-[#0e151e]" />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-3 2xl:grid-cols-[minmax(0,1fr)_290px_260px]">
        <div className="h-[340px] animate-pulse rounded-xl border border-[#263241] bg-[#0e151e]" />
        <div className="h-[340px] animate-pulse rounded-xl border border-[#263241] bg-[#0e151e]" />
        <div className="h-[340px] animate-pulse rounded-xl border border-[#263241] bg-[#0e151e]" />
      </div>
      <p className="text-center text-[10px] text-slate-600">Loading persisted account data…</p>
    </main>
  );
}
