import { useQuery } from "@tanstack/react-query";
import { ArrowsClockwise, Copy } from "@phosphor-icons/react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Panel, Tag } from "@/components/Primitives";
import { TID } from "@/constants/testIds";

const WEBHOOK_PATH = "/api/webhooks/github";

const Row = ({ label, ok, value }) => (
  <div className="flex items-center gap-3 border-b border-[#1a1a1a] py-2.5 last:border-b-0">
    <span className="h-1.5 w-1.5 shrink-0" style={{ background: ok ? "#34c759" : "#ff3b30" }} />
    <span className="w-40 shrink-0 text-[10px] uppercase tracking-[0.16em] text-[#9ca3af]">{label}</span>
    <span className="min-w-0 flex-1 truncate text-[11px] text-[#6b7280]">{value}</span>
    <Tag color={ok ? "#34c759" : "#ff3b30"}>{ok ? "online" : "down"}</Tag>
  </div>
);

const copy = (text, msg) => {
  navigator.clipboard.writeText(text);
  toast.success(msg);
};

export default function Settings() {
  const { data: health, refetch, isFetching } = useQuery({
    queryKey: ["health"],
    queryFn: async () => (await api.get("/system/health")).data,
  });
  const { data: sql } = useQuery({
    queryKey: ["supabase-sql"],
    queryFn: async () => (await api.get("/system/supabase-sql")).data,
  });

  const webhookUrl = `${process.env.REACT_APP_BACKEND_URL}${WEBHOOK_PATH}`;
  const linters = health?.linters || {};

  return (
    <div data-testid={TID.settings.root} className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-[#1a1a1a] pb-5">
        <div>
          <div className="mb-2 text-[10px] uppercase tracking-[0.28em] text-[#6b7280]">Configuration</div>
          <h1 className="font-[Chivo] text-4xl font-black tracking-tighter">SYSTEM</h1>
        </div>
        <button
          data-testid={TID.settings.refresh}
          onClick={() => refetch()}
          className="flex items-center gap-1.5 border border-[#1a1a1a] px-3 py-2 text-[10px] uppercase tracking-[0.18em] text-[#6b7280] transition-colors duration-150 hover:border-[#333] hover:text-[#f3f4f6]"
        >
          <ArrowsClockwise size={12} className={isFetching ? "animate-spin" : ""} /> Re-probe
        </button>
      </header>

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel testId={TID.settings.health} title="Service Probes">
          <Row label="Gemini LLM" ok={health?.gemini?.ok} value={health?.gemini?.model} />
          <Row
            label="Supabase"
            ok={health?.supabase?.ready}
            value={health?.supabase?.detail || health?.supabase?.project}
          />
          <Row label="GitHub API" ok={health?.github?.ok} value={health?.github?.login || health?.github?.detail} />
          <Row label="MongoDB" ok={health?.mongo?.ok} value={health?.mongo?.db} />
          <Row label="Webhook secret" ok={health?.webhook_secret_set} value="HMAC SHA-256 verification" />
          <Row
            label="RAG corpus"
            ok={(health?.rag?.embedded || 0) > 0}
            value={`${health?.rag?.embedded || 0}/${health?.rag?.policies || 0} chunks · ${health?.rag?.dimensions || 0} dims`}
          />
        </Panel>

        <Panel title="MCP Linter Sandbox">
          <p className="mb-3 text-[11px] leading-relaxed text-[#9ca3af]">
            Tools are exposed over a JSON-RPC 2.0 MCP stdio server. Each call executes in a throwaway
            temp directory with a stripped environment and a 45s wall-clock cap — PR code is parsed,
            never executed.
          </p>
          {Object.entries(linters).map(([k, v]) => (
            <Row key={k} label={k.replace("_scan", "")} ok={v} value={v ? "tool registered" : "binary missing"} />
          ))}
          <div className="mt-3 text-[10px] text-[#6b7280]">
            Self-correction cap: {health?.max_validation_attempts || 3} attempts
          </div>
        </Panel>
      </div>

      <Panel title="GitHub Webhook">
        <div className="space-y-3 text-[11px] leading-relaxed text-[#9ca3af]">
          <div>
            <span className="mb-1.5 block text-[9px] uppercase tracking-[0.22em] text-[#6b7280]">
              Payload URL
            </span>
            <div className="flex items-center gap-2">
              <code
                data-testid={TID.settings.webhookUrl}
                className="min-w-0 flex-1 truncate border border-[#1a1a1a] bg-[#050505] px-3 py-2 text-[#f3f4f6]"
              >
                {webhookUrl}
              </code>
              <button
                data-testid={TID.settings.copyWebhook}
                onClick={() => copy(webhookUrl, "Webhook URL copied")}
                className="border border-[#1a1a1a] p-2 text-[#6b7280] transition-colors duration-150 hover:border-[#333] hover:text-[#f3f4f6]"
              >
                <Copy size={13} />
              </button>
            </div>
          </div>
          <ul className="space-y-1">
            <li>· Content type: <span className="text-[#f3f4f6]">application/json</span></li>
            <li>· Events: <span className="text-[#f3f4f6]">Pull requests</span> (opened / reopened / synchronize / ready_for_review)</li>
            <li>· Secret: set in backend env as <span className="text-[#f3f4f6]">GITHUB_WEBHOOK_SECRET</span> — never exposed to the browser</li>
            <li>· Signature: <span className="text-[#f3f4f6]">X-Hub-Signature-256</span> verified with constant-time HMAC before the body is parsed</li>
            <li>· Duplicate deliveries are de-duplicated by <span className="text-[#f3f4f6]">X-GitHub-Delivery</span></li>
          </ul>
        </div>
      </Panel>

      <Panel
        testId={TID.settings.sql}
        title="Supabase Bootstrap SQL"
        right={
          <button
            data-testid={TID.settings.copySql}
            onClick={() => copy(sql?.sql || "", "SQL copied to clipboard")}
            className="flex items-center gap-1.5 border border-[#1a1a1a] px-2.5 py-1 text-[9px] uppercase tracking-[0.16em] text-[#6b7280] transition-colors duration-150 hover:border-[#333] hover:text-[#f3f4f6]"
          >
            <Copy size={11} /> Copy SQL
          </button>
        }
      >
        <pre className="max-h-80 overflow-auto border border-[#1a1a1a] bg-[#050505] p-3 text-[10px] leading-[1.7] text-[#9ca3af]">
          {sql?.sql || "loading…"}
        </pre>
      </Panel>
    </div>
  );
}
