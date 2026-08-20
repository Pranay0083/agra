import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Pulse } from "@phosphor-icons/react";
import { api, fmtMs, fmtUsd, relTime, SEV_COLOR, STATUS_COLOR } from "@/lib/api";
import { Metric, Panel, Tag, Empty } from "@/components/Primitives";
import { TID } from "@/constants/testIds";

const HealthChip = ({ label, ok, detail }) => (
  <div className="flex items-center gap-2 border border-[#1a1a1a] bg-[#0a0a0a] px-3 py-2">
    <span className="h-1.5 w-1.5" style={{ background: ok ? "#34c759" : "#ff3b30" }} />
    <span className="text-[10px] uppercase tracking-[0.16em] text-[#9ca3af]">{label}</span>
    <span className="ml-auto max-w-[130px] truncate text-[10px] text-[#6b7280]">{detail}</span>
  </div>
);

const PIPELINE = [
  { id: "supervisor", label: "Supervisor", tone: "#6e40c9" },
  { id: "tooling", label: "MCP Linters", tone: "#6e40c9" },
  { id: "rag", label: "pgvector RAG", tone: "#0366d6" },
  { id: "synthesis", label: "Synthesis", tone: "#6e40c9" },
  { id: "validator", label: "Critic ×3", tone: "#d73a49" },
  { id: "finalize", label: "Action Router", tone: "#2ea44f" },
];

export default function Overview() {
  const { data: stats } = useQuery({
    queryKey: ["analytics"],
    queryFn: async () => (await api.get("/analytics/overview")).data,
    refetchInterval: 5000,
  });
  const { data: reviews } = useQuery({
    queryKey: ["reviews", "recent"],
    queryFn: async () => (await api.get("/reviews", { params: { limit: 8 } })).data,
    refetchInterval: 3000,
  });
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: async () => (await api.get("/system/health")).data,
    refetchInterval: 60000,
  });

  const runs = reviews?.runs || [];
  const sev = stats?.severity || {};
  const running = runs.filter((r) => r.status === "RUNNING" || r.status === "QUEUED").length;

  return (
    <div data-testid={TID.overview.root} className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-[#1a1a1a] pb-5">
        <div>
          <div className="mb-2 text-[10px] uppercase tracking-[0.28em] text-[#6b7280]">
            Autonomous Pull Request Security Reviewer
          </div>
          <h1 className="font-[Chivo] text-4xl font-black leading-[0.95] tracking-tighter sm:text-5xl">
            MISSION<span className="text-[#ff3b30]">.</span>CONTROL
          </h1>
          <p className="mt-3 max-w-2xl text-xs leading-relaxed text-[#9ca3af]">
            Webhook ingestion &rarr; LangGraph fan-out &rarr; MCP-sandboxed linters + pgvector policy
            retrieval &rarr; Pydantic-validated synthesis &rarr; inline GitHub review.
          </p>
        </div>
        {running > 0 && (
          <div className="flex items-center gap-2 border border-[#007aff55] bg-[#04101c] px-3 py-2">
            <Pulse size={14} color="#007aff" className="pulse-dot" />
            <span className="text-[10px] uppercase tracking-[0.18em] text-[#7fb4ff]">
              {running} pipeline{running > 1 ? "s" : ""} in flight
            </span>
          </div>
        )}
      </header>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <Metric testId={TID.overview.kpiRuns} label="Total Runs" value={stats?.total_runs ?? "—"}
          sub={`${stats?.status_counts?.COMPLETED || 0} completed`} />
        <Metric testId={TID.overview.kpiFindings} label="Findings" value={stats?.total_findings ?? "—"}
          sub={`${Object.keys(stats?.categories || {}).length} categories`} />
        <Metric testId={TID.overview.kpiCritical} label="Critical + High"
          value={(sev.CRITICAL || 0) + (sev.HIGH || 0)} accent="#ff3b30"
          sub={`${sev.CRITICAL || 0} critical · ${sev.HIGH || 0} high`} />
        <Metric testId={TID.overview.kpiLatency} label="Avg Latency" value={fmtMs(stats?.latency?.avg_ms)}
          accent="#007aff" sub={`p95 ${fmtMs(stats?.latency?.p95_ms)}`} />
        <Metric testId={TID.overview.kpiCost} label="LLM Spend" value={fmtUsd(stats?.cost?.total_usd)}
          accent="#34c759" sub={`${(stats?.cost?.total_tokens || 0).toLocaleString()} tokens`} />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.55fr_1fr]">
        <Panel
          testId={TID.overview.feed}
          title="Live Review Feed"
          right={
            <Link
              to="/reviews"
              className="flex items-center gap-1 text-[10px] uppercase tracking-[0.18em] text-[#6b7280] transition-colors duration-150 hover:text-[#f3f4f6]"
            >
              All runs <ArrowRight size={11} />
            </Link>
          }
          className="min-h-[320px]"
        >
          {runs.length === 0 ? (
            <Empty
              title="NO RUNS YET"
              hint="Trigger the pipeline from Run Review — paste vulnerable code, or point it at a real GitHub pull request."
              action={
                <Link
                  to="/simulator"
                  className="border border-[#333] px-4 py-2 text-[10px] uppercase tracking-[0.2em] transition-colors duration-150 hover:bg-[#f3f4f6] hover:text-[#050505]"
                >
                  Run first review
                </Link>
              }
            />
          ) : (
            <ul className="-m-4">
              {runs.map((r) => (
                <li key={r.id} className="border-b border-[#1a1a1a] last:border-b-0">
                  <Link
                    to={`/reviews/${r.id}`}
                    data-testid={TID.reviews.row(r.id)}
                    className="flex items-center gap-3 px-4 py-3 transition-colors duration-150 hover:bg-[#101010]"
                  >
                    <span className="h-8 w-1" style={{ background: STATUS_COLOR[r.status] }} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[12px] text-[#f3f4f6]">
                        {r.repo_full_name}
                        {r.pr_number ? ` #${r.pr_number}` : ""}
                        <span className="ml-2 text-[#6b7280]">{r.pr_title}</span>
                      </span>
                      <span className="mt-1 flex flex-wrap items-center gap-2 text-[10px] text-[#6b7280]">
                        <Tag color={STATUS_COLOR[r.status]}>{r.status}</Tag>
                        <span>{r.source}</span>
                        <span>· {relTime(r.created_at)}</span>
                        <span>· {fmtMs(r.latency_ms)}</span>
                      </span>
                    </span>
                    <span className="shrink-0 text-right">
                      <span
                        className="block font-[Chivo] text-xl font-black leading-none"
                        style={{ color: r.risk_score > 60 ? "#ff3b30" : r.risk_score > 30 ? "#ffcc00" : "#34c759" }}
                      >
                        {r.risk_score}
                      </span>
                      <span className="text-[9px] uppercase tracking-[0.18em] text-[#6b7280]">risk</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <div className="space-y-4">
          <Panel testId={TID.overview.topology} title="Agent Topology">
            <ol className="space-y-1.5">
              {PIPELINE.map((n, i) => (
                <li key={n.id} className="flex items-center gap-3">
                  <span className="w-5 text-[10px] tabular-nums text-[#3d3d3d]">{i + 1}</span>
                  <span className="h-6 w-[3px]" style={{ background: n.tone }} />
                  <span className="text-[11px] uppercase tracking-[0.14em] text-[#c9ced6]">
                    {n.label}
                  </span>
                  {n.id === "tooling" && (
                    <span className="ml-auto text-[9px] uppercase tracking-[0.16em] text-[#6b7280]">
                      parallel
                    </span>
                  )}
                  {n.id === "rag" && (
                    <span className="ml-auto text-[9px] uppercase tracking-[0.16em] text-[#6b7280]">
                      parallel
                    </span>
                  )}
                  {n.id === "validator" && (
                    <span className="ml-auto text-[9px] uppercase tracking-[0.16em] text-[#d73a49]">
                      self-correct
                    </span>
                  )}
                </li>
              ))}
            </ol>
          </Panel>

          <Panel testId={TID.overview.health} title="System Health">
            <div className="space-y-2">
              <HealthChip label="Gemini" ok={health?.gemini?.ok} detail={health?.gemini?.model} />
              <HealthChip
                label="Supabase"
                ok={health?.supabase?.ready}
                detail={health?.supabase?.ready ? "pgvector live" : "tables missing"}
              />
              <HealthChip label="GitHub" ok={health?.github?.ok} detail={health?.github?.login || "—"} />
              <HealthChip label="MongoDB" ok={health?.mongo?.ok} detail={health?.mongo?.db} />
              <HealthChip
                label="MCP Linters"
                ok={Object.values(health?.linters || {}).some(Boolean)}
                detail={Object.entries(health?.linters || {})
                  .filter(([, v]) => v)
                  .map(([k]) => k.replace("_scan", ""))
                  .join(" ")}
              />
              <HealthChip
                label="RAG Corpus"
                ok={(health?.rag?.embedded || 0) > 0}
                detail={`${health?.rag?.embedded || 0}/${health?.rag?.policies || 0} · ${health?.rag?.dimensions || 0}d`}
              />
            </div>
          </Panel>
        </div>
      </div>

      <Panel title="Severity Distribution">
        <div className="grid grid-cols-5 gap-3">
          {["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"].map((s) => {
            const total = Object.values(sev).reduce((a, b) => a + b, 0) || 1;
            const pct = Math.round(((sev[s] || 0) / total) * 100);
            return (
              <div key={s}>
                <div className="flex items-baseline justify-between">
                  <span className="text-[10px] uppercase tracking-[0.16em]" style={{ color: SEV_COLOR[s] }}>
                    {s}
                  </span>
                  <span className="font-[Chivo] text-lg font-black">{sev[s] || 0}</span>
                </div>
                <div className="mt-2 h-1.5 w-full bg-[#151515]">
                  <div
                    className="h-full transition-[width] duration-500"
                    style={{ width: `${pct}%`, background: SEV_COLOR[s] }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </Panel>
    </div>
  );
}
