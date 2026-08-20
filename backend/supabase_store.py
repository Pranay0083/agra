"""Supabase persistence + pgvector RAG over the PostgREST API.

The service_role key cannot execute DDL, so tables are provisioned either by the
user pasting BOOTSTRAP_SQL into the Supabase SQL editor, or automatically when a
Transaction Pooler URI is supplied via SUPABASE_DB_URL. Everything degrades
gracefully: Mongo always holds the authoritative copy.
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

import config

logger = logging.getLogger(__name__)

BOOTSTRAP_SQL = """-- Autonomous PR Security Reviewer :: Supabase bootstrap
create extension if not exists vector;

create table if not exists review_runs (
  id uuid primary key,
  repo_full_name text not null,
  pr_number int not null default 0,
  pr_title text,
  author text,
  head_sha text,
  html_url text,
  source text not null default 'simulation',
  status text not null,
  risk_score int not null default 0,
  summary text,
  latency_ms int not null default 0,
  prompt_tokens int not null default 0,
  completion_tokens int not null default 0,
  total_tokens int not null default 0,
  estimated_cost_usd numeric(12,6) not null default 0,
  llm_calls int not null default 0,
  llm_retries int not null default 0,
  validation_attempts int not null default 0,
  findings_count int not null default 0,
  tool_violations_count int not null default 0,
  error text,
  created_at timestamptz not null default now()
);
create index if not exists review_runs_created_idx on review_runs (created_at desc);
create index if not exists review_runs_status_idx on review_runs (status);

create table if not exists review_findings (
  id uuid primary key,
  run_id uuid not null references review_runs(id) on delete cascade,
  file_path text not null,
  line int not null,
  severity text not null,
  category text not null,
  title text not null,
  rationale text,
  cwe text,
  owasp text,
  rule_id text,
  suggested_code text,
  created_at timestamptz not null default now()
);
create index if not exists review_findings_run_idx on review_findings (run_id);
create index if not exists review_findings_sev_idx on review_findings (severity);

create table if not exists security_policies (
  id uuid primary key,
  title text not null,
  category text not null default 'OWASP',
  cwe text[] default '{}',
  content text not null,
  source text default 'builtin',
  embedding vector(768),
  created_at timestamptz not null default now()
);
create index if not exists security_policies_embedding_idx
  on security_policies using hnsw (embedding vector_cosine_ops);

create or replace function match_security_policies(
  query_embedding vector(768),
  match_count int default 5
)
returns table (
  id uuid, title text, category text, cwe text[], content text, similarity float
)
language sql stable
as $$
  select p.id, p.title, p.category, p.cwe, p.content,
         1 - (p.embedding <=> query_embedding) as similarity
  from security_policies p
  where p.embedding is not null
  order by p.embedding <=> query_embedding
  limit match_count;
$$;
"""


class SupabaseStore:
    def __init__(self):
        self.url = config.SUPABASE_URL
        self.key = config.SUPABASE_SERVICE_KEY
        self.ready = False
        self.last_error: Optional[str] = None

    @property
    def configured(self) -> bool:
        return bool(self.url and self.key)

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        h = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if extra:
            h.update(extra)
        return h

    async def health(self) -> Dict[str, Any]:
        if not self.configured:
            return {"configured": False, "ready": False, "detail": "SUPABASE_URL / SERVICE_KEY missing"}
        try:
            async with httpx.AsyncClient(timeout=15.0) as c:
                r = await c.get(f"{self.url}/rest/v1/review_runs", headers=self._headers(),
                                params={"select": "id", "limit": 1})
            if r.status_code == 200:
                self.ready = True
                self.last_error = None
                pg = await self._pgvector_ready()
                return {"configured": True, "ready": True, "pgvector": pg,
                        "detail": "tables reachable", "project": self.url}
            self.ready = False
            self.last_error = r.text[:300]
            return {"configured": True, "ready": False, "pgvector": False,
                    "detail": "tables missing - run the bootstrap SQL", "project": self.url}
        except Exception as exc:  # noqa: BLE001
            self.ready = False
            self.last_error = str(exc)[:300]
            return {"configured": True, "ready": False, "pgvector": False, "detail": self.last_error}

    async def _pgvector_ready(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=15.0) as c:
                r = await c.get(f"{self.url}/rest/v1/security_policies", headers=self._headers(),
                                params={"select": "id", "limit": 1})
            return r.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    async def _insert(self, table: str, rows: List[Dict[str, Any]]) -> bool:
        if not self.configured or not rows:
            return False
        try:
            async with httpx.AsyncClient(timeout=25.0) as c:
                r = await c.post(
                    f"{self.url}/rest/v1/{table}",
                    headers=self._headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
                    json=rows,
                )
            if r.status_code >= 400:
                self.last_error = f"{table}: {r.text[:250]}"
                return False
            return True
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)[:250]
            return False

    async def mirror_run(self, run: Dict[str, Any]) -> bool:
        m = run.get("metrics", {})
        row = {
            "id": run["id"],
            "repo_full_name": run.get("repo_full_name", ""),
            "pr_number": run.get("pr_number", 0),
            "pr_title": run.get("pr_title", ""),
            "author": run.get("author", ""),
            "head_sha": run.get("head_sha", ""),
            "html_url": run.get("html_url", ""),
            "source": run.get("source", "simulation"),
            "status": run.get("status", "QUEUED"),
            "risk_score": run.get("risk_score", 0),
            "summary": (run.get("summary") or "")[:6000],
            "latency_ms": run.get("latency_ms", 0),
            "prompt_tokens": m.get("prompt_tokens", 0),
            "completion_tokens": m.get("completion_tokens", 0),
            "total_tokens": m.get("total_tokens", 0),
            "estimated_cost_usd": m.get("estimated_cost_usd", 0.0),
            "llm_calls": m.get("llm_calls", 0),
            "llm_retries": m.get("llm_retries", 0),
            "validation_attempts": m.get("validation_attempts", 0),
            "findings_count": len(run.get("findings", [])),
            "tool_violations_count": len(run.get("tool_violations", [])),
            "error": (run.get("error") or "")[:1000] or None,
            "created_at": run.get("created_at"),
        }
        ok = await self._insert("review_runs", [row])
        if not ok:
            return False
        findings = run.get("findings", [])
        if findings:
            import uuid as _uuid

            rows = [{
                "id": str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"{run['id']}:{i}")),
                "run_id": run["id"],
                "file_path": f.get("file_path", ""),
                "line": f.get("line", 1),
                "severity": f.get("severity", "LOW"),
                "category": f.get("category", "SECURITY"),
                "title": f.get("title", ""),
                "rationale": (f.get("rationale") or "")[:4000],
                "cwe": f.get("cwe"),
                "owasp": f.get("owasp"),
                "rule_id": f.get("rule_id"),
                "suggested_code": (f.get("suggested_code") or "")[:4000] or None,
            } for i, f in enumerate(findings)]
            await self._insert("review_findings", rows)
        return True

    async def upsert_policy(self, policy: Dict[str, Any]) -> bool:
        row = {
            "id": policy["id"],
            "title": policy["title"],
            "category": policy.get("category", "OWASP"),
            "cwe": policy.get("cwe", []),
            "content": policy["content"],
            "source": policy.get("source", "builtin"),
            "embedding": policy.get("embedding") or None,
            "created_at": policy.get("created_at"),
        }
        return await self._insert("security_policies", [row])

    async def delete_policy(self, policy_id: str) -> bool:
        if not self.configured:
            return False
        try:
            async with httpx.AsyncClient(timeout=20.0) as c:
                await c.delete(f"{self.url}/rest/v1/security_policies",
                               headers=self._headers(), params={"id": f"eq.{policy_id}"})
            return True
        except Exception:  # noqa: BLE001
            return False

    async def match_policies(self, embedding: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        if not self.configured or not embedding:
            return []
        try:
            async with httpx.AsyncClient(timeout=25.0) as c:
                r = await c.post(
                    f"{self.url}/rest/v1/rpc/match_security_policies",
                    headers=self._headers(),
                    json={"query_embedding": embedding, "match_count": top_k},
                )
            if r.status_code != 200:
                return []
            return r.json()
        except Exception:  # noqa: BLE001
            return []


supabase = SupabaseStore()
