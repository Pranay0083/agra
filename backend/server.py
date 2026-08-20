import asyncio
import logging
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, FastAPI, Header, HTTPException, Query, Request
from starlette.middleware.cors import CORSMiddleware

import config
import db
import diff_utils
import graph as agent_graph
from gemini import gemini
from github_client import github, verify_signature
from mcp_client import probe_tools
from policies_seed import BUILTIN_POLICIES
from samples import SAMPLES
from schemas import (
    GithubReviewRequest,
    PolicyChunk,
    PolicyCreate,
    PolicySearchRequest,
    ReviewRun,
    SimulateRequest,
)
from supabase_store import BOOTSTRAP_SQL, supabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Autonomous PR Security Reviewer")
api = APIRouter(prefix="/api")

SEV_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------- system


@api.get("/")
async def root():
    return {"service": "autonomous-pr-security-reviewer", "status": "online", "model": config.GEMINI_MODEL}


@api.get("/system/health")
async def system_health():
    gem, gh, sb, tools = await asyncio.gather(
        gemini.ping(), github.whoami(), supabase.health(), probe_tools(),
    )
    try:
        await db.client.admin.command("ping")
        mongo_ok = True
    except Exception:  # noqa: BLE001
        mongo_ok = False
    policy_count = await db.policies.count_documents({})
    embedded = await db.policies.count_documents({"embedding.0": {"$exists": True}})
    return {
        "gemini": {"ok": gem["ok"], "model": config.GEMINI_MODEL, "detail": gem.get("detail")},
        "github": gh,
        "supabase": sb,
        "mongo": {"ok": mongo_ok, "db": config.DB_NAME},
        "linters": tools,
        "webhook_secret_set": bool(config.GITHUB_WEBHOOK_SECRET),
        "webhook_url": "/api/webhooks/github",
        "rag": {"policies": policy_count, "embedded": embedded, "dimensions": config.EMBED_DIM},
        "max_validation_attempts": config.MAX_VALIDATION_ATTEMPTS,
    }


@api.get("/system/graph")
async def system_graph():
    return {"nodes": agent_graph.GRAPH_TOPOLOGY, "max_attempts": config.MAX_VALIDATION_ATTEMPTS}


@api.get("/system/supabase-sql")
async def supabase_sql():
    return {"sql": BOOTSTRAP_SQL}


@api.get("/samples")
async def samples():
    return {"samples": SAMPLES}


# -------------------------------------------------------------------- reviews


async def _create_run(**kwargs) -> ReviewRun:
    run = ReviewRun(**kwargs)
    await db.runs.insert_one(run.model_dump())
    return run


async def _collect_github_files(owner: str, repo: str, number: int, head_sha: str) -> List[Dict[str, Any]]:
    files = await github.list_files(owner, repo, number)
    out: List[Dict[str, Any]] = []
    for f in files[:40]:
        if f.get("status") == "removed":
            continue
        path = f["filename"]
        lang = diff_utils.detect_language(path)
        parsed = diff_utils.parse_patch(f.get("patch", ""))
        content = ""
        if lang in ("python", "javascript"):
            content = await github.get_file_content(owner, repo, path, head_sha)
        out.append({
            "path": path, "language": lang, "patch": f.get("patch", ""),
            "added_lines": parsed["added_lines"], "content": content,
        })
    return out


@api.post("/reviews/simulate")
async def simulate(req: SimulateRequest, background: BackgroundTasks):
    lang = diff_utils.detect_language(req.file_path)
    if lang not in ("python", "javascript"):
        raise HTTPException(422, "Only .py / .js / .jsx / .ts / .tsx files can be analysed.")
    patch = diff_utils.synth_full_add_patch(req.content)
    parsed = diff_utils.parse_patch(patch)
    files = [{
        "path": req.file_path, "language": lang, "patch": patch,
        "added_lines": parsed["added_lines"], "content": req.content,
    }]
    run = await _create_run(
        source="simulation", repo_full_name=req.repo_full_name, pr_number=req.pr_number,
        pr_title=req.pr_title, author=req.author, head_sha="simulated",
    )
    background.add_task(agent_graph.execute_run, run.id, req.repo_full_name, files)
    return {"run_id": run.id, "status": "QUEUED"}


@api.post("/reviews/github")
async def review_github_pr(req: GithubReviewRequest, background: BackgroundTasks):
    if not github.configured:
        raise HTTPException(400, "GITHUB_TOKEN is not configured.")
    try:
        pr = await github.get_pull(req.owner, req.repo, req.pull_number)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    head_sha = pr["head"]["sha"]
    repo_full = f"{req.owner}/{req.repo}"
    files = await _collect_github_files(req.owner, req.repo, req.pull_number, head_sha)
    run = await _create_run(
        source="manual", repo_full_name=repo_full, pr_number=req.pull_number,
        pr_title=pr.get("title", ""), author=(pr.get("user") or {}).get("login", ""),
        head_sha=head_sha, html_url=pr.get("html_url", ""),
    )

    async def _job():
        await agent_graph.execute_run(run.id, repo_full, files)
        if req.publish:
            try:
                await _publish(run.id)
            except Exception:  # noqa: BLE001
                logger.warning("auto-publish failed for %s", run.id)

    background.add_task(_job)
    return {"run_id": run.id, "status": "QUEUED", "files": len(files), "head_sha": head_sha}


@api.get("/reviews")
async def list_reviews(limit: int = Query(50, ge=1, le=200), status: Optional[str] = None):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    docs = await db.runs.find(q, {"_id": 0, "changed_files": 0, "tool_violations": 0,
                                  "retrieved_policies": 0}).sort("created_at", -1).to_list(limit)
    return {"runs": docs}


@api.get("/reviews/{run_id}")
async def get_review(run_id: str):
    doc = await db.runs.find_one({"id": run_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Review run not found")
    return doc


@api.delete("/reviews/{run_id}")
async def delete_review(run_id: str):
    res = await db.runs.delete_one({"id": run_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Review run not found")
    return {"deleted": True}


async def _publish(run_id: str) -> Dict[str, Any]:
    doc = await db.runs.find_one({"id": run_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Review run not found")
    if doc.get("source") == "simulation" or not doc.get("pr_number"):
        raise HTTPException(400, "This run is a local simulation and has no pull request to publish to.")
    if doc.get("status") != "COMPLETED":
        raise HTTPException(400, f"Run status is {doc.get('status')}; only COMPLETED runs can be published.")

    owner, _, repo = doc["repo_full_name"].partition("/")
    findings = doc.get("findings", [])
    comments = [{
        "path": f["file_path"],
        "line": f["line"],
        "side": "RIGHT",
        "body": _comment_body(f),
    } for f in findings]

    header = (
        f"### Autonomous Security Review\n\n"
        f"**Risk score:** `{doc.get('risk_score', 0)}/100` · "
        f"**Findings:** `{len(findings)}` · "
        f"**Latency:** `{doc.get('latency_ms', 0)} ms` · "
        f"**Model:** `{config.GEMINI_MODEL}`\n\n{doc.get('summary', '')}\n\n"
        f"<sub>Generated by a LangGraph multi-agent pipeline (Supervisor → MCP linters + pgvector RAG → "
        f"Synthesis → Pydantic validator).</sub>"
    )
    result = await github.post_review(owner, repo, doc["pr_number"], doc["head_sha"], header, comments)
    url = result.get("html_url")
    await db.runs.update_one({"id": run_id}, {"$set": {"published": True, "github_review_url": url}})
    return {"published": True, "github_review_url": url, "degraded": result.get("_degraded")}


def _comment_body(f: Dict[str, Any]) -> str:
    tags = " ".join(filter(None, [
        f"`{f.get('severity')}`", f"`{f.get('category')}`",
        f"`{f['cwe']}`" if f.get("cwe") else None,
        f"`{f['rule_id']}`" if f.get("rule_id") else None,
    ]))
    body = f"**{f.get('title')}**\n\n{tags}\n\n{f.get('rationale', '')}"
    if f.get("owasp"):
        body += f"\n\n_OWASP:_ {f['owasp']}"
    if f.get("policy_citation"):
        body += f"\n\n_Policy:_ {f['policy_citation']}"
    if f.get("suggested_code"):
        body += f"\n\n```suggestion\n{f['suggested_code']}\n```"
    return body


@api.post("/reviews/{run_id}/publish")
async def publish_review(run_id: str):
    return await _publish(run_id)


# ------------------------------------------------------------------- webhooks


@api.post("/webhooks/github")
async def github_webhook(
    request: Request,
    background: BackgroundTasks,
    x_hub_signature_256: Optional[str] = Header(default=None),
    x_github_event: Optional[str] = Header(default=None),
    x_github_delivery: Optional[str] = Header(default=None),
):
    raw = await request.body()
    if not verify_signature(raw, x_hub_signature_256):
        raise HTTPException(403, "Invalid or missing X-Hub-Signature-256")

    payload = await request.json()
    if x_github_event == "ping":
        return {"pong": True}
    if x_github_event != "pull_request":
        return {"ignored": True, "reason": f"event {x_github_event}"}
    if payload.get("action") not in {"opened", "reopened", "synchronize", "ready_for_review"}:
        return {"ignored": True, "reason": f"action {payload.get('action')}"}

    if x_github_delivery:
        existing = await db.deliveries.find_one({"delivery_id": x_github_delivery})
        if existing:
            return {"duplicate": True, "run_id": existing.get("run_id")}

    pr = payload.get("pull_request") or {}
    repo = payload.get("repository") or {}
    owner = ((repo.get("owner") or {}).get("login") or "").strip()
    name = repo.get("name")
    number = payload.get("number") or pr.get("number")
    head_sha = (pr.get("head") or {}).get("sha")
    if not (owner and name and number and head_sha):
        raise HTTPException(400, "Malformed pull_request payload: repository.owner.login, "
                                 "repository.name, number and pull_request.head.sha are required")

    run = await _create_run(
        source="webhook", repo_full_name=repo.get("full_name") or f"{owner}/{name}", pr_number=number,
        pr_title=pr.get("title", ""), author=(pr.get("user") or {}).get("login", ""),
        head_sha=head_sha, html_url=pr.get("html_url", ""),
    )
    if x_github_delivery:
        await db.deliveries.insert_one({
            "delivery_id": x_github_delivery, "run_id": run.id, "received_at": _now(),
        })

    async def _job():
        try:
            files = await _collect_github_files(owner, name, number, head_sha)
            await agent_graph.execute_run(run.id, repo.get("full_name") or f"{owner}/{name}", files)
            await _publish(run.id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("webhook pipeline failed")
            await db.runs.update_one({"id": run.id}, {"$set": {"status": "ERROR", "error": str(exc)[:500]}})

    background.add_task(_job)
    return {"accepted": True, "run_id": run.id, "delivery_id": x_github_delivery}


# ------------------------------------------------------------------- policies


@api.get("/policies")
async def list_policies():
    docs = await db.policies.find({}, {"_id": 0, "embedding": 0}).sort("created_at", 1).to_list(500)
    embedded = await db.policies.count_documents({"embedding.0": {"$exists": True}})
    return {"policies": docs, "embedded": embedded, "total": len(docs)}


@api.post("/policies")
async def create_policy(body: PolicyCreate):
    policy = PolicyChunk(**body.model_dump(), source="custom")
    try:
        policy.embedding = await gemini.embed(f"{policy.title}\n{policy.content}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("embedding failed: %s", exc)
    doc = policy.model_dump()
    await db.policies.insert_one(dict(doc))
    asyncio.create_task(supabase.upsert_policy(doc))
    doc.pop("embedding", None)
    return doc


@api.delete("/policies/{policy_id}")
async def delete_policy(policy_id: str):
    res = await db.policies.delete_one({"id": policy_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Policy not found")
    asyncio.create_task(supabase.delete_policy(policy_id))
    return {"deleted": True}


@api.post("/policies/search")
async def search_policies(body: PolicySearchRequest):
    try:
        vector = await gemini.embed(body.query)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Embedding failed: {str(exc)[:200]}") from exc

    remote = await supabase.match_policies(vector, top_k=body.top_k)
    if remote:
        return {"backend": "supabase-pgvector", "results": [{
            "id": str(r["id"]), "title": r["title"], "category": r["category"],
            "cwe": r.get("cwe") or [], "content": r["content"],
            "score": round(float(r.get("similarity", 0)), 4),
        } for r in remote]}

    docs = await db.policies.find({}, {"_id": 0}).to_list(500)
    scored = [(agent_graph._cosine(vector, d["embedding"]), d) for d in docs if d.get("embedding")]
    scored.sort(key=lambda x: x[0], reverse=True)
    return {"backend": "mongo-cosine", "results": [{
        "id": d["id"], "title": d["title"], "category": d["category"],
        "cwe": d.get("cwe", []), "content": d["content"], "score": round(s, 4),
    } for s, d in scored[: body.top_k]]}


@api.post("/policies/seed")
async def seed_policies(force: bool = False):
    count = await db.policies.count_documents({})
    if count and not force:
        return {"seeded": 0, "existing": count}
    if force:
        await db.policies.delete_many({"source": "builtin"})
    created = 0
    for item in BUILTIN_POLICIES:
        policy = PolicyChunk(**item, source="builtin")
        try:
            policy.embedding = await gemini.embed(f"{policy.title}\n{policy.content}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("seed embedding failed: %s", exc)
        doc = policy.model_dump()
        await db.policies.insert_one(dict(doc))
        asyncio.create_task(supabase.upsert_policy(doc))
        created += 1
    return {"seeded": created}


# ------------------------------------------------------------------ analytics


@api.get("/analytics/overview")
async def analytics_overview():
    docs = await db.runs.find({}, {"_id": 0, "changed_files": 0, "content": 0}).sort("created_at", -1).to_list(500)

    severity = Counter()
    cwe = Counter()
    tools = Counter()
    categories = Counter()
    by_day: Dict[str, Counter] = defaultdict(Counter)

    total_cost = 0.0
    total_tokens = 0
    latencies: List[int] = []
    retries = 0
    attempts_hist = Counter()

    for d in docs:
        m = d.get("metrics", {}) or {}
        total_cost += float(m.get("estimated_cost_usd", 0) or 0)
        total_tokens += int(m.get("total_tokens", 0) or 0)
        retries += int(m.get("llm_retries", 0) or 0)
        attempts_hist[str(m.get("validation_attempts", 0) or 0)] += 1
        if d.get("latency_ms"):
            latencies.append(d["latency_ms"])
        day = (d.get("created_at") or "")[:10]
        rule_map = {str(v.get("rule_id", "")).lower(): v.get("tool", "")
                    for v in d.get("tool_violations", [])}
        for f in d.get("findings", []):
            severity[f.get("severity", "INFO")] += 1
            categories[f.get("category", "SECURITY")] += 1
            if f.get("cwe"):
                cwe[f["cwe"]] += 1
            tools[_attribute(f.get("rule_id"), rule_map)] += 1
            by_day[day][f.get("severity", "INFO")] += 1

    status_counts = Counter(d.get("status", "QUEUED") for d in docs)
    open_findings = sum(severity.values())

    timeline = [{
        "date": day,
        **{s: by_day[day].get(s, 0) for s in SEV_ORDER},
        "total": sum(by_day[day].values()),
    } for day in sorted(by_day)][-14:]

    return {
        "total_runs": len(docs),
        "status_counts": dict(status_counts),
        "total_findings": open_findings,
        "severity": {s: severity.get(s, 0) for s in SEV_ORDER},
        "categories": dict(categories),
        "top_cwe": [{"cwe": k, "count": v} for k, v in cwe.most_common(8)],
        "tool_attribution": [{"tool": k, "count": v} for k, v in tools.most_common(8)],
        "timeline": timeline,
        "cost": {
            "total_usd": round(total_cost, 6),
            "total_tokens": total_tokens,
            "avg_usd_per_run": round(total_cost / len(docs), 6) if docs else 0,
        },
        "latency": {
            "avg_ms": int(sum(latencies) / len(latencies)) if latencies else 0,
            "p95_ms": int(sorted(latencies)[int(len(latencies) * 0.95) - 1]) if latencies else 0,
            "max_ms": max(latencies) if latencies else 0,
        },
        "resilience": {
            "llm_retries": retries,
            "attempts_histogram": dict(attempts_hist),
            "failed_validation": status_counts.get("FAILED_VALIDATION", 0),
            "errors": status_counts.get("ERROR", 0),
        },
    }


def _attribute(rule_id: Optional[str], rule_map: Dict[str, str]) -> str:
    """Attribute a finding to the linter that produced its rule id."""
    if not rule_id:
        return "llm-synthesis"
    raw = rule_id.strip().lower()
    tail = raw.split("/")[-1]
    for key in (raw, tail):
        if key in rule_map and rule_map[key]:
            return rule_map[key]
    if raw.startswith("llm-"):
        return "llm-synthesis"
    for tool in ("bandit", "semgrep", "eslint", "pattern"):
        if raw.startswith(tool):
            return tool
    if len(tail) > 1 and tail[0] == "b" and tail[1:].isdigit():
        return "bandit"
    if tail.startswith(("js-", "py-")):
        return "pattern"
    if tail.startswith(("python-", "javascript-")):
        return "semgrep"
    return "llm-synthesis"


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await db.ensure_indexes()
    asyncio.create_task(_bootstrap())


async def _bootstrap():
    try:
        if await db.policies.count_documents({}) == 0:
            logger.info("seeding built-in security policy corpus")
            await seed_policies()
            logger.info("policy corpus ready")
        await supabase.health()
    except Exception:  # noqa: BLE001
        logger.warning("bootstrap incomplete", exc_info=False)


@app.on_event("shutdown")
async def shutdown():
    db.client.close()
