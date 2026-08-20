import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, GithubLogo, Trash, UploadSimple } from "@phosphor-icons/react";
import { toast } from "sonner";
import { api, fmtMs, fmtUsd, fmtTime, SEV_COLOR, STATUS_COLOR } from "@/lib/api";
import { AgentTrace } from "@/components/AgentTrace";
import { FindingCard } from "@/components/FindingCard";
import { Empty, Metric, Panel, Tag } from "@/components/Primitives";
import { TID } from "@/constants/testIds";

const TABS = ["findings", "linters", "rag", "diff"];

export default function ReviewDetail() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [tab, setTab] = useState("findings");

  const { data: run, isLoading } = useQuery({
    queryKey: ["review", runId],
    queryFn: async () => (await api.get(`/reviews/${runId}`)).data,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "RUNNING" || s === "QUEUED" ? 1500 : false;
    },
  });

  const publish = useMutation({
    mutationFn: async () => (await api.post(`/reviews/${runId}/publish`)).data,
    onSuccess: (d) => {
      toast.success(d.degraded ? `Posted (degraded): ${d.degraded}` : "Inline review posted to GitHub");
      qc.invalidateQueries({ queryKey: ["review", runId] });
    },
    onError: (e) => toast.error(e?.response?.data?.detail || "Publish failed"),
  });

  const remove = useMutation({
    mutationFn: async () => (await api.delete(`/reviews/${runId}`)).data,
    onSuccess: () => {
      toast.success("Run deleted");
      navigate("/reviews");
    },
  });

  if (isLoading || !run) {
    return (
      <div className="py-24 text-center text-[11px] uppercase tracking-[0.24em] text-[#6b7280]">
        <span className="cursor-blink">loading run</span>
      </div>
    );
  }

  const m = run.metrics || {};
  const files = run.changed_files || [];
  const contentFor = (p) => files.find((f) => f.path === p)?.content;

  return (
    <div data-testid={TID.detail.root} className="space-y-6">
      <header className="border-b border-[#1a1a1a] pb-5">
        <Link
          to="/reviews"
          data-testid={TID.detail.back}
          className="mb-4 inline-flex items-center gap-1.5 text-[10px] uppercase tracking-[0.2em] text-[#6b7280] transition-colors duration-150 hover:text-[#f3f4f6]"
        >
          <ArrowLeft size={11} /> Back to runs
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Tag testId={TID.detail.status} color={STATUS_COLOR[run.status]} solid>
                {run.status.replace("_", " ")}
              </Tag>
              <Tag color="#6b7280">{run.source}</Tag>
              {run.published && <Tag color="#34c759">published</Tag>}
              <span className="text-[10px] text-[#6b7280]">{fmtTime(run.created_at)}</span>
            </div>
            <h1 className="font-[Chivo] text-2xl font-black tracking-tighter sm:text-3xl">
              {run.repo_full_name}
              {run.pr_number ? <span className="text-[#6b7280]"> #{run.pr_number}</span> : null}
            </h1>
            <p className="mt-1.5 max-w-3xl text-xs text-[#9ca3af]">{run.pr_title || "—"}</p>
            {run.summary && (
              <p className="mt-3 max-w-3xl border-l-2 border-[#333] pl-3 text-[12px] leading-relaxed text-[#c9ced6]">
                {run.summary}
              </p>
            )}
          </div>
          <div className="flex items-center gap-3">
            <div data-testid={TID.detail.risk} className="border border-[#1a1a1a] px-5 py-3 text-center">
              <div
                className="font-[Chivo] text-4xl font-black leading-none"
                style={{ color: run.risk_score > 60 ? "#ff3b30" : run.risk_score > 30 ? "#ffcc00" : "#34c759" }}
              >
                {run.risk_score}
              </div>
              <div className="mt-1 text-[9px] uppercase tracking-[0.2em] text-[#6b7280]">risk / 100</div>
            </div>
            <div className="flex flex-col gap-2">
              {run.html_url && (
                <a
                  href={run.html_url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-2 border border-[#1a1a1a] px-3 py-2 text-[10px] uppercase tracking-[0.16em] text-[#9ca3af] transition-colors duration-150 hover:border-[#333] hover:text-[#f3f4f6]"
                >
                  <GithubLogo size={13} /> Open PR
                </a>
              )}
              <button
                data-testid={TID.detail.publish}
                disabled={run.source === "simulation" || run.status !== "COMPLETED" || publish.isPending}
                onClick={() => publish.mutate()}
                className="flex items-center gap-2 border border-[#2ea44f] px-3 py-2 text-[10px] uppercase tracking-[0.16em] text-[#2ea44f] transition-colors duration-150 hover:bg-[#2ea44f] hover:text-[#050505] disabled:cursor-not-allowed disabled:border-[#1a1a1a] disabled:text-[#3d3d3d] disabled:hover:bg-transparent"
              >
                <UploadSimple size={13} /> {publish.isPending ? "Posting…" : "Post inline review"}
              </button>
              <button
                data-testid={TID.detail.delete}
                onClick={() => remove.mutate()}
                className="flex items-center gap-2 border border-[#1a1a1a] px-3 py-2 text-[10px] uppercase tracking-[0.16em] text-[#6b7280] transition-colors duration-150 hover:border-[#ff3b30] hover:text-[#ff3b30]"
              >
                <Trash size={13} /> Delete
              </button>
            </div>
          </div>
        </div>
      </header>

      {run.error && (
        <div className="border border-[#ff3b3055] bg-[#160707] px-4 py-3 text-[11px] text-[#ff8a80]">
          <strong className="uppercase tracking-[0.18em]">Exhaustion fallback · </strong>
          {run.error}
        </div>
      )}

      <div data-testid={TID.detail.metrics} className="grid grid-cols-2 gap-4 lg:grid-cols-6">
        <Metric label="Latency" value={fmtMs(run.latency_ms)} accent="#007aff" />
        <Metric label="Findings" value={(run.findings || []).length} />
        <Metric label="Linter Hits" value={(run.tool_violations || []).length} accent="#ffcc00" />
        <Metric label="Attempts" value={`${m.validation_attempts || 0}/3`} accent={m.validation_attempts > 1 ? "#ffcc00" : "#34c759"} />
        <Metric label="Tokens" value={(m.total_tokens || 0).toLocaleString()} sub={`${m.llm_calls || 0} calls · ${m.llm_retries || 0} retries`} />
        <Metric label="Cost" value={fmtUsd(m.estimated_cost_usd)} accent="#34c759" />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_1.5fr]">
        <AgentTrace trace={run.trace || []} status={run.status} />

        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {TABS.map((t) => (
              <button
                key={t}
                data-testid={TID.detail.tab(t)}
                onClick={() => setTab(t)}
                className={`border px-3 py-1.5 text-[10px] uppercase tracking-[0.18em] transition-colors duration-150 ${
                  tab === t
                    ? "border-[#f3f4f6] bg-[#f3f4f6] text-[#050505]"
                    : "border-[#1a1a1a] text-[#6b7280] hover:border-[#333] hover:text-[#f3f4f6]"
                }`}
              >
                {t === "rag" ? "RAG context" : t}
              </button>
            ))}
          </div>

          {tab === "findings" && (
            <div data-testid={TID.detail.findings} className="space-y-3">
              {(run.findings || []).length === 0 ? (
                <Empty
                  title="NO FINDINGS"
                  hint={
                    run.status === "RUNNING"
                      ? "Agents are still working through the diff."
                      : "The synthesis agent found nothing actionable in the changed lines."
                  }
                />
              ) : (
                run.findings.map((f, i) => (
                  <FindingCard key={i} finding={f} index={i} fileContent={contentFor(f.file_path)} />
                ))
              )}
            </div>
          )}

          {tab === "linters" && (
            <Panel testId={TID.detail.tools} title="Deterministic MCP Linter Violations">
              {(run.tool_violations || []).length === 0 ? (
                <p className="text-[11px] text-[#6b7280]">No linter output for this diff.</p>
              ) : (
                <ul className="-m-4 divide-y divide-[#1a1a1a]">
                  {run.tool_violations.map((v, i) => (
                    <li key={i} className="flex items-start gap-3 px-4 py-2.5">
                      <span className="mt-0.5 h-3 w-1" style={{ background: SEV_COLOR[v.severity] || "#6b7280" }} />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <Tag color="#9ca3af">{v.tool}</Tag>
                          <span className="text-[11px] text-[#f3f4f6]">{v.rule_id}</span>
                          {v.cwe && <Tag color="#007aff">{v.cwe}</Tag>}
                          {!v.in_diff && <Tag color="#3d3d3d">outside diff</Tag>}
                          <span className="ml-auto text-[10px] text-[#6b7280]">
                            {v.file_path}:{v.line}
                          </span>
                        </div>
                        <p className="mt-1 text-[11px] leading-relaxed text-[#9ca3af]">{v.message}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          )}

          {tab === "rag" && (
            <Panel testId={TID.detail.policies} title="Retrieved Security Policies (cosine similarity)">
              {(run.retrieved_policies || []).length === 0 ? (
                <p className="text-[11px] text-[#6b7280]">No policies retrieved.</p>
              ) : (
                <ul className="space-y-3">
                  {run.retrieved_policies.map((p) => (
                    <li key={p.id} className="border-l-2 border-[#0366d6] pl-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-[12px] text-[#f3f4f6]">{p.title}</span>
                        <Tag color="#0366d6">{p.score}</Tag>
                        <Tag color="#3d3d3d">{p.backend}</Tag>
                        {(p.cwe || []).map((c) => (
                          <Tag key={c} color="#6b7280">
                            {c}
                          </Tag>
                        ))}
                      </div>
                      <p className="mt-1 text-[11px] leading-relaxed text-[#6b7280]">{p.content}</p>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          )}

          {tab === "diff" && (
            <Panel title="Changed Files">
              {files.length === 0 ? (
                <p className="text-[11px] text-[#6b7280]">No files captured.</p>
              ) : (
                <ul className="space-y-4">
                  {files.map((f) => (
                    <li key={f.path}>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-[12px] text-[#f3f4f6]">{f.path}</span>
                        <Tag color="#9ca3af">{f.language}</Tag>
                        <Tag color="#34c759">+{(f.added_lines || []).length}</Tag>
                        {f.skipped_reason && <Tag color="#3d3d3d">{f.skipped_reason}</Tag>}
                      </div>
                      {f.patch && (
                        <pre className="mt-2 max-h-72 overflow-auto border border-[#1a1a1a] bg-[#050505] p-3 text-[11px] leading-[1.7]">
                          {f.patch.split("\n").map((l, i) => (
                            <div
                              key={i}
                              className="whitespace-pre px-1"
                              style={
                                l.startsWith("+")
                                  ? { background: "rgba(52,199,89,0.09)", color: "#8fe3ac" }
                                  : l.startsWith("-")
                                    ? { background: "rgba(255,59,48,0.09)", color: "#ff9b93" }
                                    : l.startsWith("@@")
                                      ? { color: "#007aff" }
                                      : { color: "#6b7280" }
                              }
                            >
                              {l}
                            </div>
                          ))}
                        </pre>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          )}
        </div>
      </div>

      {(run.validation_errors || []).length > 0 && (
        <Panel title="Validator Rejections (self-correction feedback)">
          <ul className="space-y-1.5">
            {run.validation_errors.map((e, i) => (
              <li key={i} className="text-[11px] leading-relaxed text-[#ff9b93]">
                · {e}
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}
