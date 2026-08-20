# PRD — Autonomous Pull Request Security Reviewer ("Sentry Graph")

## 1. Original problem statement (verbatim intent)
Build a system that automatically inspects incoming pull requests for security vulnerabilities,
logic flaws and memory leaks. It orchestrates a multi-agent workflow triggered by GitHub webhooks,
runs secure linters via the Model Context Protocol (MCP), cross-references findings with a vector
database (RAG), and posts structured, inline code reviews back to the pull request.

Specified stack: Gemini (LLM) · LangGraph + LangChain (agents) · FastAPI (API) · MCP + sandbox
(tools) · Supabase PostgreSQL + pgvector (DB/vector store) · Pydantic v2 (validation) · React
(dashboard).

Flow: Webhook ingestion → HMAC verify + diff parse → LangGraph state machine (Supervisor →
parallel Tooling + RAG → Synthesis) → Pydantic critic with a self-correction loop capped at N=3 →
persistence of cost/latency/vulnerability metrics → inline delivery via the GitHub REST API.

## 2. User choices captured
- LLM: user's own Google AI Studio key. `gemini-2.0-flash` was **retired by Google on 2026-06-01**
  (key returns 404 with "use gemini-3.6-flash"), so **gemini-3.6-flash** is the default, set via
  `GEMINI_MODEL`.
- DB: user's own Supabase project (URL + service_role + Transaction Pooler URI).
- GitHub: user's own PAT (`AgrapujyaLashkari`) + generated webhook secret.
- Linters: Bandit + Semgrep **plus ESLint / JS pattern rules** for JavaScript diffs.
- Dashboard: all three priorities (reviews feed + agent trace timeline, vulnerability analytics,
  security policy manager).

## 3. Architecture as built
```
GitHub PR ──webhook──▶ FastAPI /api/webhooks/github
                        │ constant-time HMAC SHA-256 on the RAW body
                        │ X-GitHub-Delivery de-duplication
                        ▼
              LangGraph StateGraph (graph.py)
                START ▶ supervisor
                          ├──▶ tooling  (MCP stdio JSON-RPC → bandit / semgrep / eslint / pattern)
                          └──▶ rag      (Gemini embeddings → Supabase pgvector cosine RPC)
                                   ▼ (fan-in)
                              synthesis (Gemini + responseSchema, tenacity 3× exp-backoff)
                                   ▼
                              validator (Pydantic v2 + line-anchor critic)
                          valid ─▶ finalize ─▶ Action Router
                        invalid & attempts<3 ─▶ synthesis   (self-correction loop)
                        attempts>=3 ─▶ exhausted ─▶ FAILED_VALIDATION
                                   ▼
        MongoDB (authoritative, live trace)  +  Supabase mirror (review_runs, review_findings)
                                   ▼
        GitHub REST: POST /pulls/{n}/reviews with inline `line`/`side` comments + ```suggestion```
```

### Backend modules (`/app/backend`)
| File | Role |
|---|---|
| `server.py` | FastAPI routes, webhook, publish, analytics, policies |
| `graph.py` | LangGraph state machine, all 4 agents + critic + trace persistence |
| `mcp_security_server.py` | MCP JSON-RPC 2.0 stdio server; sandboxed linter tools |
| `mcp_client.py` | MCP stdio client + `probe_tools()` health check |
| `gemini.py` | Gemini generate (JSON responseSchema) + embeddings, tenacity retries, cost model |
| `supabase_store.py` | PostgREST mirror, pgvector `match_security_policies` RPC, `BOOTSTRAP_SQL` |
| `github_client.py` | HMAC verify, PR files/diff/contents, inline review posting with fallback |
| `schemas.py` | Pydantic v2 contracts (`ReviewDraft`, `PatchComment`, `ReviewRun`, …) |
| `diff_utils.py` | Unified-diff hunk parser, added-line map, numbered source rendering |
| `policies_seed.py` | 15-chunk OWASP/CWE RAG corpus |
| `samples.py` | Deliberately vulnerable Python + JS demo snippets |

### Frontend (`/app/frontend/src`)
Terminal / retro-futurist dark console — Chivo headings, JetBrains Mono body, void-black `#050505`,
1px hairline grid, sharp (0-radius) controls, scanline animation on running graph nodes.
Pages: `Overview`, `Reviews`, `ReviewDetail`, `Simulator` (Run Review), `Analytics`, `Policies`,
`Settings`.

## 4. Core requirements (static)
1. HMAC-verified webhook ingestion with delivery de-duplication.
2. Stateful multi-agent orchestration with true parallel fan-out and conditional routing.
3. Linters executed behind a standardized MCP tool interface in an isolated sandbox.
4. Vector retrieval of security policies (cosine similarity) feeding the synthesis prompt.
5. Strict Pydantic v2 output contract with a self-correction loop capped at 3 attempts and a
   graceful `FAILED_VALIDATION` exhaustion state.
6. Tenacity exponential-backoff retries (3 attempts) on every Gemini call.
7. Cost / latency / token / vulnerability metrics persisted and charted.
8. Inline review delivery to the originating pull request.

## 5. Implemented — 2026-08-20
- [x] FastAPI backend with 19 `/api` endpoints; MongoDB authoritative store + Supabase mirror.
- [x] Supabase provisioned automatically over the pooler: `review_runs`, `review_findings`,
      `security_policies` (vector 768) + `match_security_policies()` RPC + **hnsw** cosine index.
- [x] MCP stdio server exposing `bandit_scan`, `semgrep_scan`, `eslint_scan`, `pattern_scan`;
      local offline Semgrep ruleset (`semgrep_rules/security.yaml`), 14 JS + 4 Python pattern rules.
- [x] LangGraph graph with parallel Tooling/RAG branches, synthesis, Pydantic critic, 3-attempt
      self-correction loop, exhaustion fallback, per-node live trace written to Mongo.
- [x] Gemini `gemini-3.6-flash` with `responseSchema` structured output + `gemini-embedding-001`
      (768d); tenacity retry; token & USD cost accounting.
- [x] GitHub webhook (HMAC, dedupe, malformed-payload 400), manual PR analysis, inline review
      posting with graceful summary-only fallback when line anchors are rejected.
- [x] React dashboard: live feed, agent trace timeline, findings with highlighted code + suggested
      patches, linter/RAG/diff tabs, analytics charts, policy manager with similarity probe,
      settings/health console.
- [x] Testing agent regression: **19/19 backend cases pass, all frontend flows pass**.

## 6. Backlog
### P0
- Persist a queue/worker (Celery/RQ) so webhook processing survives a backend restart.
- Repository allow-list + per-repo enable/disable in the dashboard.

### P1
- Supabase Realtime / WebSocket push instead of 1.5–8s polling.
- Multi-file PR batching with per-file token budgeting for very large diffs.
- Re-review on `synchronize` diffing only the new commits.
- Auth on the dashboard (currently open) before any public deployment.

### P2
- GitHub App installation flow instead of a user PAT.
- Semgrep Pro / registry rulesets when network egress is allowed.
- Trend baselines and per-author security scorecards.
- Export findings as SARIF for GitHub code scanning.

## 7. Next tasks
1. Point a real repository's webhook at `/api/webhooks/github` and validate an end-to-end
   opened-PR → inline comment cycle.
2. Add repository allow-listing before enabling auto-publish org-wide.
3. Replace polling with Supabase Realtime for the live feed.

## 8. Known constraints
- Docker-in-Docker is unavailable in this container, so the MCP Tooling Agent runs linters as
  sandboxed subprocesses (throwaway temp dir, stripped env, 45s cap) behind the same MCP interface
  a Docker sandbox would expose.
- The dashboard has **no authentication**; it is a single-operator console.
