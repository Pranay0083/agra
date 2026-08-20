import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowsClockwise } from "@phosphor-icons/react";
import { api, fmtMs, fmtUsd, relTime, STATUS_COLOR } from "@/lib/api";
import { Empty, Tag } from "@/components/Primitives";
import { TID } from "@/constants/testIds";

const FILTERS = ["ALL", "COMPLETED", "RUNNING", "FAILED_VALIDATION", "ERROR"];

export default function Reviews() {
  const [filter, setFilter] = useState("ALL");
  const { data, refetch, isFetching } = useQuery({
    queryKey: ["reviews", filter],
    queryFn: async () =>
      (await api.get("/reviews", { params: { limit: 200, ...(filter !== "ALL" ? { status: filter } : {}) } })).data,
    refetchInterval: 4000,
  });

  const runs = data?.runs || [];

  return (
    <div data-testid={TID.reviews.root} className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-[#1a1a1a] pb-5">
        <div>
          <div className="mb-2 text-[10px] uppercase tracking-[0.28em] text-[#6b7280]">Audit Log</div>
          <h1 className="font-[Chivo] text-4xl font-black tracking-tighter">REVIEW RUNS</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {FILTERS.map((f) => (
            <button
              key={f}
              data-testid={TID.reviews.filter(f)}
              onClick={() => setFilter(f)}
              className={`border px-3 py-1.5 text-[10px] uppercase tracking-[0.16em] transition-colors duration-150 ${
                filter === f
                  ? "border-[#f3f4f6] bg-[#f3f4f6] text-[#050505]"
                  : "border-[#1a1a1a] text-[#6b7280] hover:border-[#333] hover:text-[#f3f4f6]"
              }`}
            >
              {f.replace("_", " ")}
            </button>
          ))}
          <button
            data-testid={TID.reviews.refresh}
            onClick={() => refetch()}
            className="flex items-center gap-1.5 border border-[#1a1a1a] px-3 py-1.5 text-[10px] uppercase tracking-[0.16em] text-[#6b7280] transition-colors duration-150 hover:border-[#333] hover:text-[#f3f4f6]"
          >
            <ArrowsClockwise size={12} className={isFetching ? "animate-spin" : ""} /> Sync
          </button>
        </div>
      </header>

      <div data-testid={TID.reviews.table} className="border border-[#1a1a1a] bg-[#0a0a0a]">
        <div className="hidden grid-cols-[1.7fr_0.7fr_0.6fr_0.5fr_0.6fr_0.6fr_0.6fr] gap-3 border-b border-[#1a1a1a] px-4 py-2.5 text-[9px] uppercase tracking-[0.2em] text-[#6b7280] lg:grid">
          <span>Repository / PR</span>
          <span>Status</span>
          <span>Source</span>
          <span>Risk</span>
          <span>Findings</span>
          <span>Latency</span>
          <span>Cost</span>
        </div>
        {runs.length === 0 ? (
          <Empty title="EMPTY QUEUE" hint="No review runs match this filter." />
        ) : (
          runs.map((r) => (
            <Link
              key={r.id}
              to={`/reviews/${r.id}`}
              data-testid={TID.reviews.row(r.id)}
              className="grid grid-cols-2 gap-3 border-b border-[#1a1a1a] px-4 py-3 transition-colors duration-150 last:border-b-0 hover:bg-[#101010] lg:grid-cols-[1.7fr_0.7fr_0.6fr_0.5fr_0.6fr_0.6fr_0.6fr]"
            >
              <span className="col-span-2 min-w-0 lg:col-span-1">
                <span className="block truncate text-[12px]">
                  {r.repo_full_name}
                  {r.pr_number ? ` #${r.pr_number}` : ""}
                </span>
                <span className="block truncate text-[10px] text-[#6b7280]">
                  {r.pr_title || "—"} · {relTime(r.created_at)}
                </span>
              </span>
              <span className="flex items-center">
                <Tag color={STATUS_COLOR[r.status]}>{r.status.replace("_", " ")}</Tag>
              </span>
              <span className="flex items-center text-[11px] text-[#9ca3af]">{r.source}</span>
              <span
                className="flex items-center font-[Chivo] text-sm font-black"
                style={{ color: r.risk_score > 60 ? "#ff3b30" : r.risk_score > 30 ? "#ffcc00" : "#34c759" }}
              >
                {r.risk_score}
              </span>
              <span className="flex items-center text-[11px] tabular-nums text-[#9ca3af]">
                {(r.findings || []).length}
              </span>
              <span className="flex items-center text-[11px] tabular-nums text-[#9ca3af]">
                {fmtMs(r.latency_ms)}
              </span>
              <span className="flex items-center text-[11px] tabular-nums text-[#9ca3af]">
                {fmtUsd(r.metrics?.estimated_cost_usd)}
              </span>
            </Link>
          ))
        )}
      </div>
    </div>
  );
}
