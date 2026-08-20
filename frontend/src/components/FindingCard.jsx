import { useState } from "react";
import { CaretDown, CaretRight } from "@phosphor-icons/react";
import { SEV_COLOR } from "@/lib/api";
import { Tag } from "@/components/Primitives";
import { TID } from "@/constants/testIds";

const CodeContext = ({ content, line }) => {
  if (!content) return null;
  const lines = content.split("\n");
  const start = Math.max(0, line - 4);
  const end = Math.min(lines.length, line + 3);
  return (
    <pre className="mt-3 overflow-x-auto border border-[#1a1a1a] bg-[#050505] p-3 text-[11px] leading-[1.7]">
      {lines.slice(start, end).map((l, i) => {
        const n = start + i + 1;
        const hit = n === line;
        return (
          <div
            key={n}
            className="whitespace-pre"
            style={
              hit
                ? { background: "rgba(255,59,48,0.13)", borderLeft: "2px solid #ff3b30", paddingLeft: 6 }
                : { paddingLeft: 8 }
            }
          >
            <span className="mr-3 select-none text-[#3d3d3d]">{String(n).padStart(4, " ")}</span>
            <span className={hit ? "text-[#ffb4ae]" : "text-[#9ca3af]"}>{l}</span>
          </div>
        );
      })}
    </pre>
  );
};

export const FindingCard = ({ finding, index, fileContent }) => {
  const [open, setOpen] = useState(index < 3);
  const color = SEV_COLOR[finding.severity] || "#6b7280";

  return (
    <article
      data-testid={TID.detail.finding(index)}
      className="border border-[#1a1a1a] bg-[#0a0a0a] transition-colors duration-150 hover:border-[#333]"
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start gap-3 px-4 py-3 text-left focus:outline-none focus:ring-2 focus:ring-[#007aff]"
      >
        <span className="mt-1 block h-3 w-1" style={{ background: color }} />
        {open ? (
          <CaretDown size={13} className="mt-1 shrink-0 text-[#6b7280]" />
        ) : (
          <CaretRight size={13} className="mt-1 shrink-0 text-[#6b7280]" />
        )}
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-[Chivo] text-sm font-bold tracking-tight">{finding.title}</span>
            <Tag color={color} solid>
              {finding.severity}
            </Tag>
            <Tag color="#9ca3af">{finding.category}</Tag>
            {finding.cwe && <Tag color="#007aff">{finding.cwe}</Tag>}
            {finding.rule_id && <Tag color="#6b7280">{finding.rule_id}</Tag>}
          </span>
          <span className="mt-1 block truncate text-[11px] text-[#6b7280]">
            {finding.file_path}:{finding.line}
            {finding.owasp ? ` · ${finding.owasp}` : ""}
          </span>
        </span>
      </button>

      {open && (
        <div className="border-t border-[#1a1a1a] px-4 py-3">
          <p className="text-[12px] leading-relaxed text-[#c9ced6]">{finding.rationale}</p>
          <CodeContext content={fileContent} line={finding.line} />
          {finding.suggested_code && (
            <div className="mt-3">
              <div className="mb-1.5 text-[10px] uppercase tracking-[0.2em] text-[#34c759]">
                Suggested patch
              </div>
              <pre className="overflow-x-auto border border-[#34c75933] bg-[#04140a] p-3 text-[11px] leading-[1.7] text-[#a7f3c0]">
                {finding.suggested_code}
              </pre>
            </div>
          )}
          {finding.policy_citation && (
            <div className="mt-3 border-l-2 border-[#007aff] bg-[#04101c] px-3 py-2 text-[11px] text-[#9ec5ff]">
              <span className="uppercase tracking-[0.18em] text-[#6b7280]">RAG policy · </span>
              {finding.policy_citation}
            </div>
          )}
        </div>
      )}
    </article>
  );
};
