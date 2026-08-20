import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MagnifyingGlass, Plus, Trash } from "@phosphor-icons/react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Empty, Panel, Tag } from "@/components/Primitives";
import { TID } from "@/constants/testIds";

const input =
  "w-full border border-[#1a1a1a] bg-[#050505] px-3 py-2 text-[12px] text-[#f3f4f6] outline-none transition-colors duration-150 placeholder:text-[#3d3d3d] focus:border-[#007aff] focus:ring-2 focus:ring-[#007aff33]";
const label = "mb-1.5 block text-[9px] uppercase tracking-[0.22em] text-[#6b7280]";

export default function Policies() {
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("CUSTOM");
  const [cwe, setCwe] = useState("");
  const [content, setContent] = useState("");
  const [query, setQuery] = useState("cursor.execute an SQL string built with f-string interpolation");
  const [results, setResults] = useState(null);

  const { data } = useQuery({
    queryKey: ["policies"],
    queryFn: async () => (await api.get("/policies")).data,
  });

  const create = useMutation({
    mutationFn: async () =>
      (
        await api.post("/policies", {
          title,
          category,
          cwe: cwe.split(",").map((s) => s.trim()).filter(Boolean),
          content,
        })
      ).data,
    onSuccess: () => {
      toast.success("Policy embedded and indexed");
      setTitle("");
      setCwe("");
      setContent("");
      qc.invalidateQueries({ queryKey: ["policies"] });
    },
    onError: (e) => toast.error(e?.response?.data?.detail?.[0]?.msg || "Could not add policy"),
  });

  const remove = useMutation({
    mutationFn: async (id) => (await api.delete(`/policies/${id}`)).data,
    onSuccess: () => {
      toast.success("Policy removed");
      qc.invalidateQueries({ queryKey: ["policies"] });
    },
  });

  const seed = useMutation({
    mutationFn: async () => (await api.post("/policies/seed", null, { params: { force: true } })).data,
    onSuccess: (d) => {
      toast.success(`Re-seeded ${d.seeded} built-in policies`);
      qc.invalidateQueries({ queryKey: ["policies"] });
    },
  });

  const search = useMutation({
    mutationFn: async () => (await api.post("/policies/search", { query, top_k: 5 })).data,
    onSuccess: (d) => setResults(d),
    onError: (e) => toast.error(e?.response?.data?.detail || "Search failed"),
  });

  const policies = data?.policies || [];

  return (
    <div data-testid={TID.policies.root} className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-[#1a1a1a] pb-5">
        <div>
          <div className="mb-2 text-[10px] uppercase tracking-[0.28em] text-[#6b7280]">
            Retrieval Corpus · pgvector
          </div>
          <h1 className="font-[Chivo] text-4xl font-black tracking-tighter">SECURITY POLICIES</h1>
          <p className="mt-3 text-xs text-[#9ca3af]">
            {data?.embedded || 0} of {data?.total || 0} chunks embedded · cosine similarity feeds the RAG agent
          </p>
        </div>
        <button
          data-testid={TID.policies.seed}
          onClick={() => seed.mutate()}
          disabled={seed.isPending}
          className="border border-[#1a1a1a] px-3 py-2 text-[10px] uppercase tracking-[0.18em] text-[#6b7280] transition-colors duration-150 hover:border-[#333] hover:text-[#f3f4f6]"
        >
          {seed.isPending ? "Re-seeding…" : "Re-seed OWASP corpus"}
        </button>
      </header>

      <div className="grid gap-4 xl:grid-cols-[1.45fr_1fr]">
        <Panel testId={TID.policies.list} title={`Corpus (${policies.length})`} className="min-h-[400px]">
          {policies.length === 0 ? (
            <Empty title="EMPTY CORPUS" hint="Seed the built-in OWASP corpus or add a custom policy." />
          ) : (
            <ul className="-m-4 divide-y divide-[#1a1a1a]">
              {policies.map((p) => (
                <li
                  key={p.id}
                  data-testid={TID.policies.item(p.id)}
                  className="group px-4 py-3 transition-colors duration-150 hover:bg-[#101010]"
                >
                  <div className="flex items-start gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-[12px] text-[#f3f4f6]">{p.title}</span>
                        <Tag color={p.category === "OWASP" ? "#0366d6" : "#6e40c9"}>{p.category}</Tag>
                        {(p.cwe || []).map((c) => (
                          <Tag key={c} color="#6b7280">
                            {c}
                          </Tag>
                        ))}
                      </div>
                      <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-[#6b7280]">
                        {p.content}
                      </p>
                    </div>
                    <button
                      data-testid={TID.policies.delete(p.id)}
                      onClick={() => remove.mutate(p.id)}
                      className="shrink-0 border border-transparent p-1.5 text-[#3d3d3d] transition-colors duration-150 hover:border-[#ff3b30] hover:text-[#ff3b30]"
                      aria-label={`Delete ${p.title}`}
                    >
                      <Trash size={13} />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <div className="space-y-4">
          <Panel title="Similarity Probe">
            <span className={label}>Query text</span>
            <textarea
              data-testid={TID.policies.searchInput}
              className={`${input} h-24 resize-y`}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button
              data-testid={TID.policies.searchBtn}
              onClick={() => search.mutate()}
              disabled={search.isPending || query.trim().length < 3}
              className="mt-3 flex items-center gap-2 border border-[#007aff] px-4 py-2 text-[10px] uppercase tracking-[0.2em] text-[#007aff] transition-colors duration-150 hover:bg-[#007aff] hover:text-[#050505] disabled:cursor-not-allowed disabled:border-[#1a1a1a] disabled:text-[#3d3d3d]"
            >
              <MagnifyingGlass size={13} /> {search.isPending ? "Embedding…" : "Run cosine search"}
            </button>

            {results && (
              <div data-testid={TID.policies.searchResults} className="mt-4 space-y-2">
                <div className="text-[9px] uppercase tracking-[0.2em] text-[#6b7280]">
                  backend · {results.backend}
                </div>
                {results.results.map((r) => (
                  <div key={r.id} className="border-l-2 border-[#007aff] pl-3">
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] text-[#f3f4f6]">{r.title}</span>
                      <Tag color="#007aff">{r.score}</Tag>
                    </div>
                    <p className="mt-0.5 line-clamp-2 text-[10px] text-[#6b7280]">{r.content}</p>
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <Panel title="Add Custom Policy">
            <div className="space-y-3">
              <div>
                <span className={label}>Title</span>
                <input
                  data-testid={TID.policies.addTitle}
                  className={input}
                  placeholder="Internal: no raw SQL in service layer"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <span className={label}>Category</span>
                  <input
                    data-testid={TID.policies.addCategory}
                    className={input}
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                  />
                </div>
                <div>
                  <span className={label}>CWE ids (comma separated)</span>
                  <input
                    data-testid={TID.policies.addCwe}
                    className={input}
                    placeholder="CWE-89, CWE-564"
                    value={cwe}
                    onChange={(e) => setCwe(e.target.value)}
                  />
                </div>
              </div>
              <div>
                <span className={label}>Policy body</span>
                <textarea
                  data-testid={TID.policies.addContent}
                  className={`${input} h-32 resize-y`}
                  placeholder="Describe the rule, the exploit it prevents and the required remediation…"
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                />
              </div>
              <button
                data-testid={TID.policies.addBtn}
                onClick={() => create.mutate()}
                disabled={title.trim().length < 3 || content.trim().length < 10 || create.isPending}
                className="flex items-center gap-2 border border-[#34c759] px-4 py-2 text-[10px] uppercase tracking-[0.2em] text-[#34c759] transition-colors duration-150 hover:bg-[#34c759] hover:text-[#050505] disabled:cursor-not-allowed disabled:border-[#1a1a1a] disabled:text-[#3d3d3d]"
              >
                <Plus size={13} /> {create.isPending ? "Embedding…" : "Add & embed"}
              </button>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
