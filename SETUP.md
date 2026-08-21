# Local Setup Guide

Run **Sentry Graph** (Autonomous Pull Request Security Reviewer) on your own machine.
Target time: ~15 minutes, all services on free tiers.

---

## 1. Prerequisites

| Requirement | Version | Check |
|---|---|---|
| Python | 3.11 (3.10+ works, 3.11 recommended) | `python3 --version` |
| Node.js | 20.x | `node --version` |
| Yarn | 1.22.x (**not npm**) | `yarn --version` |
| MongoDB | 6.0+ running locally, or a free Atlas cluster | `mongod --version` |
| Git | any | `git --version` |

Install Yarn if missing:
```bash
npm install -g yarn
```

Install MongoDB locally:
```bash
# macOS
brew tap mongodb/brew && brew install mongodb-community && brew services start mongodb-community

# Ubuntu / Debian
sudo apt-get install -y mongodb && sudo systemctl start mongodb

# Docker (any OS)
docker run -d --name sentry-mongo -p 27017:27017 mongo:7
```

---

## 2. Clone and create the Python environment

```bash
git clone https://github.com/<your-user>/AI_Code_Reviewer.git
cd AI_Code_Reviewer

python3.11 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r backend/requirements.txt
```

`requirements.txt` already pins `langgraph`, `langchain-google-genai`, `bandit`, `semgrep`,
`asyncpg`, `tenacity`, `motor` and everything else the agents need.

### 2a. Install the ESLint binary (JavaScript diffs)

The MCP Tooling Agent shells out to a global `eslint`:

```bash
npm install -g eslint
eslint --version                     # expect v9.x
```

Skip this and JavaScript pull requests still work — Semgrep and the built-in JS pattern rules cover
them, and `/api/system/health` will simply report `eslint_scan: false`.

### 2b. Verify the linters resolve

```bash
which bandit semgrep eslint
```

All three must be on your `PATH`. If you installed Python packages inside a venv, activate it before
starting the backend — the MCP server inherits the interpreter's `bin/` directory.

---

## 3. Get your credentials

### Google AI Studio (LLM + embeddings) — free tier
1. Open <https://aistudio.google.com/apikey>
2. **Create API key**, copy it once.
3. Confirm which flash model your key can reach:
   ```bash
   curl -s "https://generativelanguage.googleapis.com/v1beta/models?key=YOUR_KEY" \
     | grep -o '"models/gemini[^"]*"' | head -20
   ```
   > `gemini-2.0-flash` was retired by Google on **2026-06-01**. This project defaults to
   > `gemini-3.6-flash`; set `GEMINI_MODEL` to whatever your key lists.

### Supabase (PostgreSQL + pgvector) — free tier
1. Create a project at <https://supabase.com/dashboard>.
2. **Project Settings → API**: copy the **Project URL** and the **`service_role`** secret
   (not `anon`).
3. **Connect → Transaction Pooler**: copy the URI (port **6543**, host
   `aws-0-<region>.pooler.supabase.com`).
   - URL-encode special characters in the password. An `@` becomes `%40`:
     `...postgres.abcd:MyP%40ss@aws-0-...`
   - Do **not** use the Direct Connection URI (port 5432) — it needs an IPv4 add-on and will fail
     with `could not translate host name`.

### GitHub
1. Fine-grained token at <https://github.com/settings/personal-access-tokens/new> with
   **Pull requests: Read and write** + **Metadata: Read** (or a classic token with `repo`).
2. Generate a webhook secret:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

---

## 4. Configure environment files

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

Fill in `backend/.env`:

```dotenv
MONGO_URL="mongodb://localhost:27017"
DB_NAME="sentry_graph"
CORS_ORIGINS="http://localhost:3000"

GOOGLE_API_KEY="AQ.xxxxxxxxxxxxxxxx"
GEMINI_MODEL="gemini-3.6-flash"
GEMINI_EMBED_MODEL="gemini-embedding-001"
EMBED_DIM="768"
GEMINI_PRICE_INPUT_PER_M="0.30"
GEMINI_PRICE_OUTPUT_PER_M="2.50"

SUPABASE_URL="https://xxxxxxxx.supabase.co"
SUPABASE_SERVICE_KEY="eyJhbGciOi..."
SUPABASE_DB_URL="postgresql://postgres.xxxxxxxx:PASS%40WORD@aws-0-<region>.pooler.supabase.com:6543/postgres"

GITHUB_TOKEN="github_pat_..."
GITHUB_WEBHOOK_SECRET="the-secret-you-generated"

MAX_VALIDATION_ATTEMPTS="3"
```

And `frontend/.env`:

```dotenv
REACT_APP_BACKEND_URL=http://localhost:8001
WDS_SOCKET_PORT=3000
ENABLE_HEALTH_CHECK=false
```

> `SUPABASE_URL` must be the **base** URL. If you copied `https://xxxx.supabase.co/rest/v1/`, the
> app strips the suffix automatically, but the bare host is cleaner.

**Never commit these files.** `.gitignore` already excludes `.env` and `**/.env`.

---

## 5. Provision Supabase (pgvector + tables)

One command, using the pooler URI you just configured:

```bash
python scripts/bootstrap_supabase.py
```

Expected output:
```
connected: PostgreSQL 17.x ...
applied bootstrap SQL
tables: review_findings, review_runs, security_policies
match_security_policies(): present
vector extension: present
```

**Manual alternative** (no pooler URI): start the backend, open
`http://localhost:8001/api/system/supabase-sql`, copy the SQL, and run it in the Supabase
**SQL Editor**. The dashboard also exposes a *Copy SQL* button under **Settings**.

What it creates:
- extension `vector`
- `review_runs` — one row per pipeline execution with cost/latency/token metrics
- `review_findings` — one row per inline comment
- `security_policies` — the RAG corpus, `embedding vector(768)` + **hnsw** cosine index
- `match_security_policies(query_embedding, match_count)` — the similarity RPC

> If you change `EMBED_DIM`, update the `vector(768)` columns and the RPC signature to match.

---

## 6. Run the app

Two terminals.

**Terminal 1 — backend**
```bash
source .venv/bin/activate
cd backend
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

On first boot it embeds and seeds the 15 built-in OWASP/CWE policy chunks. Watch for:
```
INFO  seeding built-in security policy corpus
INFO  policy corpus ready
```

**Terminal 2 — frontend**
```bash
cd frontend
yarn install
yarn start
```

Open <http://localhost:3000>.

---

## 7. Verify the install

```bash
curl -s http://localhost:8001/api/system/health | python3 -m json.tool
```

A healthy response:
```json
{
  "gemini":   { "ok": true, "model": "gemini-3.6-flash" },
  "github":   { "ok": true, "login": "your-handle" },
  "supabase": { "configured": true, "ready": true, "pgvector": true },
  "mongo":    { "ok": true, "db": "sentry_graph" },
  "linters":  { "bandit_scan": true, "semgrep_scan": true,
                "eslint_scan": true, "pattern_scan": true },
  "rag":      { "policies": 15, "embedded": 15, "dimensions": 768 }
}
```

Then run the pipeline end to end from the UI: **Run Review → python-flask → Execute agent graph**.
You should land on the run detail page and watch Supervisor → Tooling ‖ RAG → Synthesis → Validator
→ Action Router turn green, ending in ~30–60s with a `COMPLETED` status and ~8 findings.

---

## 8. Receive real GitHub webhooks locally

GitHub cannot reach `localhost`, so tunnel it.

**Option A — ngrok**
```bash
ngrok http 8001
# → https://a1b2c3d4.ngrok-free.app
```

**Option B — smee.io** (no account)
```bash
npm install -g smee-client
smee --url https://smee.io/new-channel-id --target http://localhost:8001/api/webhooks/github
```

Then in your repository → **Settings → Webhooks → Add webhook**:

| Field | Value |
|---|---|
| Payload URL | `https://<tunnel-host>/api/webhooks/github` |
| Content type | `application/json` |
| Secret | the same value as `GITHUB_WEBHOOK_SECRET` |
| SSL verification | **Enabled** |
| Events | *Let me select individual events* → **Pull requests** only |

Do **not** choose "Send me everything". Handled actions: `opened`, `reopened`, `synchronize`,
`ready_for_review`.

Test the signature path without GitHub:
```bash
SECRET='your-webhook-secret'
BODY='{"zen":"Keep it logically awesome."}'
SIG="sha256=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')"

curl -i -X POST http://localhost:8001/api/webhooks/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: ping" \
  -H "X-Hub-Signature-256: $SIG" \
  -d "$BODY"                      # → 200 {"pong":true}

curl -i -X POST http://localhost:8001/api/webhooks/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: ping" \
  -d "$BODY"                      # → 403 invalid signature
```

You can also skip webhooks entirely: **Run Review → Live GitHub Pull Request** analyses any PR your
token can read, with an optional *post inline comments* toggle.

---

## 9. Project layout

```
backend/
  server.py                 FastAPI routes, webhook, publish, analytics, policies
  graph.py                  LangGraph state machine + the four agents + critic
  mcp_security_server.py    MCP JSON-RPC 2.0 stdio server (sandboxed linters)
  mcp_client.py             MCP stdio client + tool health probe
  gemini.py                 Gemini generate/embed, tenacity retries, cost model
  supabase_store.py         PostgREST mirror, pgvector RPC, BOOTSTRAP_SQL
  github_client.py          HMAC verify, PR files/diff, inline review posting
  schemas.py                Pydantic v2 contracts
  diff_utils.py             Unified-diff hunk parser
  policies_seed.py          15-chunk OWASP/CWE corpus
  samples.py                Vulnerable demo snippets
  semgrep_rules/            Offline Semgrep ruleset
frontend/src/
  pages/                    Overview, Reviews, ReviewDetail, Simulator, Analytics, Policies, Settings
  components/               Layout, AgentTrace, FindingCard, Primitives
  constants/testIds.js      Every data-testid used by the UI and tests
scripts/
  bootstrap_supabase.py     Applies the pgvector DDL
```

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `health.linters.bandit_scan: false` | binary not on the interpreter's `PATH` | activate the venv **before** launching uvicorn; `pip install bandit semgrep` |
| `eslint_scan: false` | ESLint not installed globally | `npm install -g eslint` (optional) |
| `semgrep` crashes with `No module named 'sse_starlette'` | Semgrep imports the MCP SDK | `pip install --no-deps "sse-starlette==2.1.3"` |
| `supabase.ready: false, "tables missing"` | DDL not applied | run `python scripts/bootstrap_supabase.py` |
| `could not translate host name "db.xxx.supabase.co"` | Direct Connection URI | use the **Transaction Pooler** URI on port 6543 |
| `asyncpg.InvalidPasswordError` | unescaped `@`/`#` in the DB password | URL-encode it (`@` → `%40`) |
| pgvector search returns fewer rows than `match_count` | ivfflat index on a tiny table | the bootstrap uses **hnsw**; re-run it if you created ivfflat manually |
| Gemini `404 ... no longer available` | retired model | set `GEMINI_MODEL` to a model your key lists (step 3) |
| Gemini `503 high demand` | transient | tenacity retries 3× with backoff; try a `-lite` model |
| Frontend calls `undefined/api/...` | missing frontend env | set `REACT_APP_BACKEND_URL` and **restart** `yarn start` |
| CORS error in the browser | origin not allowed | add `http://localhost:3000` to `CORS_ORIGINS` |
| Webhook always 403 | secret mismatch, or a proxy rewrote the body | the HMAC is over the **raw** bytes — never re-serialize before verifying |
| Findings say "not a changed line" | expected | the critic rejects bad anchors and retries up to 3× before `FAILED_VALIDATION` |

---

## 11. Security checklist before you deploy

- [ ] `.env` files are git-ignored (already configured) — verify with `git check-ignore -v backend/.env`
- [ ] Rotate any key that was ever pasted into a chat, issue or screenshot
- [ ] Restrict `CORS_ORIGINS` to your real frontend origin, never `*` with credentials
- [ ] The dashboard ships **without authentication** — put it behind auth or a private network
- [ ] Scope the GitHub token to only the repositories the reviewer should touch
- [ ] Keep Supabase Row Level Security in mind if you ever expose the `anon` key (this app uses
      `service_role` server-side only)
