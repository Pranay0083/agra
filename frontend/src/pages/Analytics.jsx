import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, fmtMs, fmtUsd, SEV_COLOR } from "@/lib/api";
import { Metric, Panel, Empty } from "@/components/Primitives";
import { TID } from "@/constants/testIds";

const TOOL_COLORS = ["#6e40c9", "#0366d6", "#ffcc00", "#34c759", "#ff3b30", "#9ca3af"];

const tipStyle = {
  background: "#0a0a0a",
  border: "1px solid #1a1a1a",
  borderRadius: 0,
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 11,
  color: "#f3f4f6",
};

export default function Analytics() {
  const { data } = useQuery({
    queryKey: ["analytics"],
    queryFn: async () => (await api.get("/analytics/overview")).data,
    refetchInterval: 8000,
  });

  const sev = data?.severity || {};
  const sevData = Object.entries(sev).map(([name, value]) => ({ name, value }));
  const cwe = data?.top_cwe || [];
  const tools = data?.tool_attribution || [];
  const timeline = data?.timeline || [];
  const hasData = (data?.total_runs || 0) > 0;

  return (
    <div data-testid={TID.analytics.root} className="space-y-6">
      <header className="border-b border-[#1a1a1a] pb-5">
        <div className="mb-2 text-[10px] uppercase tracking-[0.28em] text-[#6b7280]">Telemetry</div>
        <h1 className="font-[Chivo] text-4xl font-black tracking-tighter">VULNERABILITY ANALYTICS</h1>
      </header>

      {!hasData ? (
        <Empty title="NO TELEMETRY" hint="Run at least one review to populate analytics." />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-6">
            <Metric label="Runs" value={data.total_runs} />
            <Metric label="Findings" value={data.total_findings} accent="#ffcc00" />
            <Metric label="Avg Latency" value={fmtMs(data.latency.avg_ms)} accent="#007aff" />
            <Metric label="P95 Latency" value={fmtMs(data.latency.p95_ms)} accent="#007aff" />
            <Metric label="Total Spend" value={fmtUsd(data.cost.total_usd)} accent="#34c759"
              sub={`${fmtUsd(data.cost.avg_usd_per_run)}/run`} />
            <Metric label="Tokens" value={(data.cost.total_tokens || 0).toLocaleString()} />
          </div>

          <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
            <Panel testId={TID.analytics.timeline} title="Findings Over Time (by severity)">
              <div className="h-[260px]">
                <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={200}>
                  <BarChart data={timeline}>
                    <CartesianGrid stroke="#1a1a1a" vertical={false} />
                    <XAxis dataKey="date" stroke="#3d3d3d" tick={{ fill: "#6b7280", fontSize: 10 }} />
                    <YAxis stroke="#3d3d3d" tick={{ fill: "#6b7280", fontSize: 10 }} allowDecimals={false} />
                    <Tooltip contentStyle={tipStyle} cursor={{ fill: "#ffffff08" }} />
                    {["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((s) => (
                      <Bar key={s} dataKey={s} stackId="1" fill={SEV_COLOR[s]} maxBarSize={64} />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Panel>

            <Panel testId={TID.analytics.severity} title="Severity Distribution">
              <div className="h-[260px]">
                <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={200}>
                  <BarChart data={sevData} layout="vertical" margin={{ left: 12 }}>
                    <CartesianGrid stroke="#1a1a1a" horizontal={false} />
                    <XAxis type="number" stroke="#3d3d3d" tick={{ fill: "#6b7280", fontSize: 10 }} allowDecimals={false} />
                    <YAxis type="category" dataKey="name" width={72} stroke="#3d3d3d" tick={{ fill: "#6b7280", fontSize: 10 }} />
                    <Tooltip contentStyle={tipStyle} cursor={{ fill: "#ffffff08" }} />
                    <Bar dataKey="value" barSize={18}>
                      {sevData.map((d) => (
                        <Cell key={d.name} fill={SEV_COLOR[d.name]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Panel>
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <Panel testId={TID.analytics.cwe} title="Top CWE Classes">
              {cwe.length === 0 ? (
                <p className="text-[11px] text-[#6b7280]">No CWE tags yet.</p>
              ) : (
                <ul className="space-y-2.5">
                  {cwe.map((c) => {
                    const max = cwe[0].count || 1;
                    return (
                      <li key={c.cwe}>
                        <div className="flex items-baseline justify-between text-[11px]">
                          <span className="text-[#c9ced6]">{c.cwe}</span>
                          <span className="tabular-nums text-[#6b7280]">{c.count}</span>
                        </div>
                        <div className="mt-1 h-1 w-full bg-[#151515]">
                          <div
                            className="h-full bg-[#ff3b30] transition-[width] duration-500"
                            style={{ width: `${(c.count / max) * 100}%` }}
                          />
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Panel>

            <Panel testId={TID.analytics.tools} title="Detection Attribution">
              <div className="h-[220px]">
                <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={200}>
                  <PieChart>
                    <Pie
                      data={tools}
                      dataKey="count"
                      nameKey="tool"
                      innerRadius={45}
                      outerRadius={78}
                      paddingAngle={2}
                      stroke="#050505"
                    >
                      {tools.map((t, i) => (
                        <Cell key={t.tool} fill={TOOL_COLORS[i % TOOL_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={tipStyle} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <ul className="mt-2 space-y-1">
                {tools.map((t, i) => (
                  <li key={t.tool} className="flex items-center gap-2 text-[10px] text-[#9ca3af]">
                    <span className="h-2 w-2" style={{ background: TOOL_COLORS[i % TOOL_COLORS.length] }} />
                    {t.tool}
                    <span className="ml-auto tabular-nums text-[#6b7280]">{t.count}</span>
                  </li>
                ))}
              </ul>
            </Panel>

            <Panel testId={TID.analytics.resilience} title="Resilience & Self-Correction">
              <dl className="space-y-3 text-[11px]">
                {[
                  ["Gemini retries (tenacity)", data.resilience.llm_retries, "#ffcc00"],
                  ["FAILED_VALIDATION runs", data.resilience.failed_validation, "#ff3b30"],
                  ["Errored runs", data.resilience.errors, "#ff3b30"],
                ].map(([k, v, c]) => (
                  <div key={k} className="flex items-center justify-between border-b border-[#1a1a1a] pb-2">
                    <dt className="text-[#9ca3af]">{k}</dt>
                    <dd className="font-[Chivo] text-lg font-black" style={{ color: c }}>
                      {v}
                    </dd>
                  </div>
                ))}
              </dl>
              <div className="mt-4">
                <div className="mb-2 text-[9px] uppercase tracking-[0.22em] text-[#6b7280]">
                  Synthesis attempts histogram
                </div>
                <div className="space-y-1.5">
                  {Object.entries(data.resilience.attempts_histogram || {})
                    .sort()
                    .map(([k, v]) => (
                      <div key={k} className="flex items-center gap-2 text-[10px]">
                        <span className="w-16 text-[#6b7280]">{k} attempt{k === "1" ? "" : "s"}</span>
                        <div className="h-1.5 flex-1 bg-[#151515]">
                          <div
                            className="h-full bg-[#007aff]"
                            style={{ width: `${(v / data.total_runs) * 100}%` }}
                          />
                        </div>
                        <span className="w-6 text-right tabular-nums text-[#9ca3af]">{v}</span>
                      </div>
                    ))}
                </div>
              </div>
            </Panel>
          </div>

          <Panel testId={TID.analytics.cost} title="Run Status Breakdown">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              {Object.entries(data.status_counts || {}).map(([k, v]) => (
                <div key={k} className="border border-[#1a1a1a] p-3">
                  <div className="text-[9px] uppercase tracking-[0.18em] text-[#6b7280]">
                    {k.replace("_", " ")}
                  </div>
                  <div className="mt-1 font-[Chivo] text-2xl font-black">{v}</div>
                </div>
              ))}
            </div>
          </Panel>
        </>
      )}
    </div>
  );
}
