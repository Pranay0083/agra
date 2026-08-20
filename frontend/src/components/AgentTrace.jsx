import { NODE_COLOR, fmtMs } from "@/lib/api";
import { TID } from "@/constants/testIds";

const ORDER = ["supervisor", "tooling", "rag", "synthesis", "validator", "finalize", "exhausted"];

const Row = ({ entry, index }) => {
  const color = NODE_COLOR[entry.status] || "#6b7280";
  const running = entry.status === "RUNNING";
  return (
    <li
      data-testid={TID.detail.node(entry.node)}
      className={`relative grid grid-cols-[26px_1fr] gap-3 border-b border-[#1a1a1a] px-4 py-3 last:border-b-0 ${
        running ? "scanline" : ""
      }`}
      style={{ animationDelay: `${index * 45}ms` }}
    >
      <div className="flex flex-col items-center">
        <span
          className={`mt-1 block h-2.5 w-2.5 ${running ? "pulse-dot" : ""}`}
          style={{ background: color }}
        />
        <span className="mt-1 w-px flex-1 bg-[#1a1a1a]" />
      </div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="font-[Chivo] text-sm font-bold tracking-tight">{entry.label}</span>
          <span className="text-[10px] uppercase tracking-[0.18em]" style={{ color }}>
            {entry.status}
          </span>
          {entry.attempt > 1 && (
            <span className="text-[10px] uppercase tracking-[0.18em] text-[#ffcc00]">
              retry {entry.attempt}
            </span>
          )}
          <span className="ml-auto text-[11px] tabular-nums text-[#6b7280]">
            {fmtMs(entry.duration_ms)}
          </span>
        </div>
        {entry.detail && (
          <p className="mt-1 break-words text-[11px] leading-relaxed text-[#9ca3af]">
            {entry.detail}
          </p>
        )}
        {entry.error && (
          <pre className="mt-2 max-h-28 overflow-auto whitespace-pre-wrap border border-[#ff3b3033] bg-[#160707] p-2 text-[10px] leading-relaxed text-[#ff8a80]">
            {entry.error}
          </pre>
        )}
      </div>
    </li>
  );
};

export const AgentTrace = ({ trace = [], status }) => {
  const seen = new Set(trace.map((t) => t.node));
  const pending = ORDER.filter((n) => !seen.has(n) && n !== "exhausted");

  return (
    <div data-testid={TID.detail.trace} className="border border-[#1a1a1a] bg-[#0a0a0a]">
      <header className="flex items-center justify-between border-b border-[#1a1a1a] px-4 py-2.5">
        <h3 className="text-xs uppercase tracking-[0.2em] text-[#9ca3af]">
          LangGraph Execution Trace
        </h3>
        <span className="text-[10px] uppercase tracking-[0.18em] text-[#6b7280]">
          {trace.length} node event{trace.length === 1 ? "" : "s"}
        </span>
      </header>
      <ul>
        {trace.map((t, i) => (
          <Row key={`${t.node}-${i}`} entry={t} index={i} />
        ))}
        {status === "RUNNING" &&
          pending.map((n) => (
            <li
              key={n}
              className="grid grid-cols-[26px_1fr] gap-3 border-b border-[#1a1a1a] px-4 py-3 opacity-40 last:border-b-0"
            >
              <span className="mt-1 block h-2.5 w-2.5 border border-[#3d3d3d]" />
              <span className="text-[11px] uppercase tracking-[0.16em] text-[#6b7280]">
                {n} · pending
              </span>
            </li>
          ))}
        {trace.length === 0 && status !== "RUNNING" && (
          <li className="px-4 py-6 text-[11px] text-[#6b7280]">No trace recorded.</li>
        )}
      </ul>
    </div>
  );
};
