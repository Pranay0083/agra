import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { GithubLogo, Lightning, Play } from "@phosphor-icons/react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Panel } from "@/components/Primitives";
import { TID } from "@/constants/testIds";

const input =
  "w-full border border-[#1a1a1a] bg-[#050505] px-3 py-2 text-[12px] text-[#f3f4f6] outline-none transition-colors duration-150 placeholder:text-[#3d3d3d] focus:border-[#007aff] focus:ring-2 focus:ring-[#007aff33]";
const label = "mb-1.5 block text-[9px] uppercase tracking-[0.22em] text-[#6b7280]";

export default function Simulator() {
  const navigate = useNavigate();
  const [repo, setRepo] = useState("acme/payments-api");
  const [path, setPath] = useState("services/user_api.py");
  const [title, setTitle] = useState("Add user lookup and restore endpoints");
  const [code, setCode] = useState("");
  const [owner, setOwner] = useState("");
  const [ghRepo, setGhRepo] = useState("");
  const [prNumber, setPrNumber] = useState("");
  const [publish, setPublish] = useState(false);

  const { data: samples } = useQuery({
    queryKey: ["samples"],
    queryFn: async () => (await api.get("/samples")).data,
  });

  useEffect(() => {
    if (!code && samples?.samples?.length) {
      setCode(samples.samples[0].content);
      setPath(samples.samples[0].file_path);
    }
  }, [samples, code]);

  const runSim = useMutation({
    mutationFn: async () =>
      (
        await api.post("/reviews/simulate", {
          repo_full_name: repo,
          pr_number: 0,
          pr_title: title,
          author: "local-dev",
          file_path: path,
          content: code,
        })
      ).data,
    onSuccess: (d) => {
      toast.success("Pipeline dispatched");
      navigate(`/reviews/${d.run_id}`);
    },
    onError: (e) => toast.error(e?.response?.data?.detail || "Failed to start"),
  });

  const runGh = useMutation({
    mutationFn: async () =>
      (
        await api.post("/reviews/github", {
          owner,
          repo: ghRepo,
          pull_number: Number(prNumber),
          publish,
        })
      ).data,
    onSuccess: (d) => {
      toast.success(`Analysing ${d.files} changed file(s)`);
      navigate(`/reviews/${d.run_id}`);
    },
    onError: (e) => toast.error(e?.response?.data?.detail || "GitHub request failed"),
  });

  return (
    <div data-testid={TID.sim.root} className="space-y-6">
      <header className="border-b border-[#1a1a1a] pb-5">
        <div className="mb-2 text-[10px] uppercase tracking-[0.28em] text-[#6b7280]">Manual Trigger</div>
        <h1 className="font-[Chivo] text-4xl font-black tracking-tighter">RUN A REVIEW</h1>
        <p className="mt-3 max-w-2xl text-xs leading-relaxed text-[#9ca3af]">
          Drive the exact same LangGraph state machine the webhook uses — either against a synthetic
          diff you paste here, or a live pull request on GitHub.
        </p>
      </header>

      <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
        <Panel
          title="Synthetic Pull Request"
          right={
            <div className="flex gap-2">
              {(samples?.samples || []).map((s) => (
                <button
                  key={s.id}
                  data-testid={TID.sim.sample(s.id)}
                  onClick={() => {
                    setCode(s.content);
                    setPath(s.file_path);
                  }}
                  className="border border-[#1a1a1a] px-2.5 py-1 text-[9px] uppercase tracking-[0.16em] text-[#6b7280] transition-colors duration-150 hover:border-[#ff3b30] hover:text-[#ff3b30]"
                >
                  {s.id}
                </button>
              ))}
            </div>
          }
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <span className={label}>Repository</span>
              <input data-testid={TID.sim.repo} className={input} value={repo} onChange={(e) => setRepo(e.target.value)} />
            </div>
            <div>
              <span className={label}>File path</span>
              <input data-testid={TID.sim.path} className={input} value={path} onChange={(e) => setPath(e.target.value)} />
            </div>
          </div>
          <div className="mt-3">
            <span className={label}>PR title</span>
            <input className={input} value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="mt-3">
            <span className={label}>Source under review (.py / .js / .jsx / .ts / .tsx)</span>
            <textarea
              data-testid={TID.sim.code}
              className={`${input} h-[340px] resize-y font-[JetBrains_Mono] leading-[1.65]`}
              spellCheck={false}
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
          </div>
          <button
            data-testid={TID.sim.run}
            disabled={!code.trim() || runSim.isPending}
            onClick={() => runSim.mutate()}
            className="mt-4 flex items-center gap-2 border border-[#ff3b30] bg-[#ff3b30] px-5 py-2.5 text-[10px] uppercase tracking-[0.22em] font-bold text-[#050505] transition-colors duration-150 hover:bg-transparent hover:text-[#ff3b30] disabled:cursor-not-allowed disabled:border-[#1a1a1a] disabled:bg-transparent disabled:text-[#3d3d3d]"
          >
            <Play size={13} weight="fill" />
            {runSim.isPending ? "Dispatching…" : "Execute agent graph"}
          </button>
        </Panel>

        <div className="space-y-4">
          <Panel title="Live GitHub Pull Request">
            <div className="space-y-3">
              <div>
                <span className={label}>Owner</span>
                <input
                  data-testid={TID.sim.ghOwner}
                  className={input}
                  placeholder="AgrapujyaLashkari"
                  value={owner}
                  onChange={(e) => setOwner(e.target.value)}
                />
              </div>
              <div>
                <span className={label}>Repository</span>
                <input
                  data-testid={TID.sim.ghRepo}
                  className={input}
                  placeholder="my-service"
                  value={ghRepo}
                  onChange={(e) => setGhRepo(e.target.value)}
                />
              </div>
              <div>
                <span className={label}>Pull request number</span>
                <input
                  data-testid={TID.sim.ghNumber}
                  className={input}
                  type="number"
                  placeholder="42"
                  value={prNumber}
                  onChange={(e) => setPrNumber(e.target.value)}
                />
              </div>
              <label className="flex cursor-pointer items-center gap-2.5 border border-[#1a1a1a] px-3 py-2">
                <input
                  data-testid={TID.sim.ghPublish}
                  type="checkbox"
                  checked={publish}
                  onChange={(e) => setPublish(e.target.checked)}
                  className="h-3.5 w-3.5 accent-[#2ea44f]"
                />
                <span className="text-[10px] uppercase tracking-[0.16em] text-[#9ca3af]">
                  Post inline comments automatically
                </span>
              </label>
              <button
                data-testid={TID.sim.ghRun}
                disabled={!owner || !ghRepo || !prNumber || runGh.isPending}
                onClick={() => runGh.mutate()}
                className="flex w-full items-center justify-center gap-2 border border-[#2ea44f] px-4 py-2.5 text-[10px] uppercase tracking-[0.2em] text-[#2ea44f] transition-colors duration-150 hover:bg-[#2ea44f] hover:text-[#050505] disabled:cursor-not-allowed disabled:border-[#1a1a1a] disabled:text-[#3d3d3d] disabled:hover:bg-transparent"
              >
                <GithubLogo size={14} />
                {runGh.isPending ? "Fetching diff…" : "Analyse pull request"}
              </button>
            </div>
          </Panel>

          <Panel title="What runs">
            <ol className="space-y-2.5 text-[11px] leading-relaxed text-[#9ca3af]">
              <li className="flex gap-3">
                <Lightning size={13} className="mt-0.5 shrink-0 text-[#6e40c9]" />
                <span>
                  <strong className="text-[#f3f4f6]">Supervisor</strong> splits executable code from
                  docs/config and opens the parallel branches.
                </span>
              </li>
              <li className="flex gap-3">
                <Lightning size={13} className="mt-0.5 shrink-0 text-[#6e40c9]" />
                <span>
                  <strong className="text-[#f3f4f6]">Tooling</strong> calls Bandit, Semgrep, ESLint and
                  pattern rules over MCP in a sandboxed temp dir.
                </span>
              </li>
              <li className="flex gap-3">
                <Lightning size={13} className="mt-0.5 shrink-0 text-[#0366d6]" />
                <span>
                  <strong className="text-[#f3f4f6]">RAG</strong> embeds the changed lines and does a
                  cosine search against Supabase pgvector.
                </span>
              </li>
              <li className="flex gap-3">
                <Lightning size={13} className="mt-0.5 shrink-0 text-[#d73a49]" />
                <span>
                  <strong className="text-[#f3f4f6]">Synthesis + Critic</strong> merges both, then the
                  validator enforces the Pydantic schema and line anchors — up to 3 retries.
                </span>
              </li>
            </ol>
          </Panel>
        </div>
      </div>
    </div>
  );
}
