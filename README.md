# Sentry Graph — Autonomous Pull Request Security Reviewer

A multi-agent system that inspects incoming pull requests for **security vulnerabilities, logic
flaws and memory leaks**. It triggers from GitHub webhooks, runs security linters through the
**Model Context Protocol (MCP)**, cross-references findings against a **pgvector** policy corpus
(RAG), and posts structured **inline code review comments** back to the pull request.

## Architecture

```
GitHub PR ──webhook──▶ FastAPI /api/webhooks/github
                        │ constant-time HMAC SHA-256 over the RAW body
                        │ X-GitHub-Delivery de-duplication
                        ▼
              LangGraph StateGraph
                START ▶ supervisor            (splits executable code from docs/config)
                          ├──▶ tooling        (MCP: bandit · semgrep · eslint · pattern rules)
                          └──▶ rag            (Gemini embeddings → Supabase pgvector cosine RPC)
                                   ▼ fan-in
                              synthesis       (Gemini, JSON responseSchema, tenacity 3× backoff)
                                   ▼
                              validator       (Pydantic v2 + line-anchor critic)
                          valid ─▶ finalize ─▶ Action Router
                        invalid & attempts<3 ─▶ synthesis        ← self-correction loop
                        attempts>=3 ─▶ exhausted ─▶ FAILED_VALIDATION
                                   ▼
        MongoDB (authoritative, live trace)  +  Supabase mirror (runs, findings, policies)
                                   ▼
        GitHub REST: POST /pulls/{n}/reviews  (inline line/side comments + ```suggestion``` blocks)
```

## Stack

| Layer | Technology |
|---|---|
| LLM engine | Google Gemini (`gemini-3.6-flash`) + `gemini-embedding-001` (768d) |
| Agent framework | LangGraph + LangChain (Python) |
| Backend API | FastAPI (Python 3.11) |
| Tool execution | MCP JSON-RPC 2.0 stdio server → Bandit, Semgrep, ESLint, pattern rules |
| Vector store | Supabase PostgreSQL + pgvector (hnsw cosine index) |
| Live store | MongoDB |
| Validation | Pydantic v2 |
| Frontend | React 19 + Tailwind + Recharts + Phosphor Icons |

> `gemini-2.0-flash` from the original design was retired by Google on 2026-06-01. The model is
> configurable via `GEMINI_MODEL`.

## Agents

1. **Supervisor (router)** — parses the diff, isolates executable code from markdown/config, opens
   the parallel branches.
2. **Static Tooling Agent** — calls linters over MCP. Every tool runs in a throwaway temp directory
   with a stripped environment and a 45s wall-clock cap. Raw stderr/JSON is normalised into
   structured rule violations tagged with severity and CWE.
3. **Security RAG Agent** — embeds the changed lines and runs a cosine similarity search against
   the `security_policies` table (OWASP Top 10 2021 + internal policies).
4. **Synthesis Agent** — merges deterministic warnings with semantic policy context into an
   actionable patch set.
5. **Validator (critic)** — enforces the Pydantic schema *and* that every comment anchors to a real
   changed line. Failures are injected back into the prompt, capped at **3 attempts**, after which
   the graph exits gracefully with `FAILED_VALIDATION`.

## Setup

**→ Full step-by-step local guide: [SETUP.md](SETUP.md)** (prerequisites, credentials, Supabase
provisioning, webhook tunnelling, verification and troubleshooting).

Quick version:

```bash
# backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
npm install -g eslint                   # optional, for JavaScript diffs
cp backend/.env.example backend/.env    # fill in your keys

# supabase schema (pgvector + tables + similarity RPC)
python scripts/bootstrap_supabase.py

# frontend
cp frontend/.env.example frontend/.env
cd frontend && yarn install
```

Run it:

```bash
cd backend && uvicorn server:app --port 8001 --reload    # terminal 1
cd frontend && yarn start                                 # terminal 2
```

Verify: `curl -s http://localhost:8001/api/system/health | python3 -m json.tool`

### Supabase provisioning
Run `python scripts/bootstrap_supabase.py` (uses `SUPABASE_DB_URL`, the **Transaction Pooler** URI
on port 6543). It creates the pgvector extension, three tables, the `match_security_policies()` RPC
and an hnsw cosine index — and is idempotent.

No pooler URI? `GET /api/system/supabase-sql` returns the same DDL; paste it into the Supabase SQL
editor. The dashboard also has a *Copy SQL* button under **Settings**.

### GitHub webhook
| Field | Value |
|---|---|
| Payload URL | `<BACKEND_URL>/api/webhooks/github` |
| Content type | `application/json` |
| Secret | same value as `GITHUB_WEBHOOK_SECRET` |
| Events | *Let me select individual events* → **Pull requests** |

Handled actions: `opened`, `reopened`, `synchronize`, `ready_for_review`.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/system/health` | Probes Gemini, GitHub, Supabase, Mongo, MCP linters, RAG corpus |
| GET | `/api/system/graph` | LangGraph topology |
| GET | `/api/system/supabase-sql` | Bootstrap DDL |
| POST | `/api/webhooks/github` | HMAC-verified webhook ingestion |
| POST | `/api/reviews/simulate` | Run the pipeline on pasted source |
| POST | `/api/reviews/github` | Run the pipeline on a live PR |
| GET | `/api/reviews` · `/api/reviews/{id}` | Run list / full run with trace |
| POST | `/api/reviews/{id}/publish` | Post the inline review to GitHub |
| GET/POST/DELETE | `/api/policies` | RAG corpus management |
| POST | `/api/policies/search` | Cosine similarity probe |
| GET | `/api/analytics/overview` | Severity, CWE, tool attribution, cost, latency, resilience |

## Dashboard

`Overview` · `Reviews` · run detail with the **LangGraph execution trace** · `Run Review`
(synthetic diff or live PR) · `Analytics` · `RAG Policies` · `Settings`.

## Security notes

- `.env` files are git-ignored. Never commit keys — use `.env.example` as the template.
- Webhook bodies are verified with `hmac.compare_digest` **before** JSON parsing.
- PR code is statically analysed, never executed.
- The dashboard ships without authentication; put it behind auth before exposing it publicly.
