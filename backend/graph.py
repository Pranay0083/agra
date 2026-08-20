"""LangGraph multi-agent orchestration for the PR security reviewer.

    START -> supervisor -> [ tooling | rag ]  (parallel fan-out)
                              \\      /
                               synthesis -> validator --valid--> finalize -> END
                                   ^            |
                                   +--invalid---+  (max 3 attempts)
                                                |
                                                +--exhausted--> END
"""
import asyncio
import logging
import operator
import time
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional, TypedDict

import numpy as np
from langgraph.graph import END, START, StateGraph
from pymongo import ReturnDocument

import config
import db
import diff_utils
from gemini import estimate_cost, gemini
from mcp_client import MCPSession
from schemas import ReviewDraft
from supabase_store import supabase

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = config.MAX_VALIDATION_ATTEMPTS

NODE_LABELS = {
    "supervisor": "1. Supervisor Agent",
    "tooling": "2. Static Tooling Agent (MCP)",
    "rag": "3. Security RAG Agent",
    "synthesis": "4. Synthesis Agent",
    "validator": "Validation Node (Critic)",
    "finalize": "Action Router",
    "exhausted": "Graceful Error Exit",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------- trace utils


async def trace_start(run_id: str, node: str, attempt: int = 1) -> int:
    entry = {
        "node": node,
        "label": NODE_LABELS.get(node, node),
        "status": "RUNNING",
        "attempt": attempt,
        "started_at": _now(),
        "ended_at": None,
        "duration_ms": 0,
        "detail": "",
        "error": None,
    }
    doc = await db.runs.find_one_and_update(
        {"id": run_id}, {"$push": {"trace": entry}},
        projection={"trace": 1, "_id": 0}, return_document=ReturnDocument.AFTER,
    )
    return len(doc["trace"]) - 1 if doc else 0


async def trace_end(run_id: str, idx: int, status: str, detail: str = "", error: Optional[str] = None,
                    started: float = 0.0):
    await db.runs.update_one({"id": run_id}, {"$set": {
        f"trace.{idx}.status": status,
        f"trace.{idx}.ended_at": _now(),
        f"trace.{idx}.duration_ms": int((time.perf_counter() - started) * 1000),
        f"trace.{idx}.detail": detail[:600],
        f"trace.{idx}.error": (error or None) and error[:800],
    }})


async def patch_run(run_id: str, patch: Dict[str, Any]):
    await db.runs.update_one({"id": run_id}, {"$set": patch})


# ---------------------------------------------------------------- graph state


class GraphState(TypedDict, total=False):
    run_id: str
    repo_full_name: str
    files: List[Dict[str, Any]]
    code_files: List[Dict[str, Any]]
    skipped_files: List[Dict[str, Any]]
    tool_violations: List[Dict[str, Any]]
    tool_notes: List[str]
    rag_policies: List[Dict[str, Any]]
    draft: Optional[Dict[str, Any]]
    validation_errors: List[str]
    attempts: int
    llm_usage: Annotated[List[Dict[str, Any]], operator.add]
    status: str
    error: Optional[str]


# ---------------------------------------------------------------- agents


async def supervisor_node(state: GraphState) -> Dict[str, Any]:
    run_id = state["run_id"]
    started = time.perf_counter()
    idx = await trace_start(run_id, "supervisor")

    code, skipped = [], []
    for f in state.get("files", []):
        lang = f.get("language") or diff_utils.detect_language(f["path"])
        f["language"] = lang
        if lang in ("python", "javascript") and f.get("content"):
            code.append(f)
        else:
            reason = "documentation/config file" if lang == "docs" else f"unsupported language ({lang})"
            if lang in ("python", "javascript") and not f.get("content"):
                reason = "file content unavailable (binary or too large)"
            f["skipped_reason"] = reason
            skipped.append(f)

    detail = f"{len(code)} executable file(s) routed to parallel branches, {len(skipped)} filtered out"
    await trace_end(run_id, idx, "SUCCESS", detail, started=started)
    await patch_run(run_id, {"status": "RUNNING"})
    return {"code_files": code, "skipped_files": skipped, "attempts": 0,
            "tool_violations": [], "rag_policies": [], "validation_errors": []}


async def tooling_node(state: GraphState) -> Dict[str, Any]:
    run_id = state["run_id"]
    started = time.perf_counter()
    idx = await trace_start(run_id, "tooling")

    violations: List[Dict[str, Any]] = []
    notes: List[str] = []
    try:
        async with MCPSession() as session:
            available = await session.list_tools()
            for f in state.get("code_files", []):
                if f["language"] == "python":
                    wanted = ["bandit_scan", "semgrep_scan", "pattern_scan"]
                else:
                    wanted = ["semgrep_scan", "eslint_scan", "pattern_scan"]
                added = set(f.get("added_lines") or [])
                for tool in wanted:
                    if tool not in available:
                        continue
                    try:
                        res = await session.call_tool(tool, {"filename": f["path"], "content": f["content"]})
                    except Exception as exc:  # noqa: BLE001
                        notes.append(f"{tool} on {f['path']}: {str(exc)[:160]}")
                        continue
                    if not res.get("available"):
                        notes.append(f"{tool} unavailable: {res.get('raw', '')[:120]}")
                        continue
                    for v in res.get("violations", []):
                        v["in_diff"] = (not added) or (v.get("line") in added)
                        v["snippet"] = v.get("snippet") or diff_utils.snippet_around(f["content"], v.get("line", 1), 1)
                        violations.append(v)
        # Prioritise violations that actually touch the diff.
        violations.sort(key=lambda v: (not v.get("in_diff"), {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}.get(v.get("severity", "LOW"), 3)))
        in_diff = sum(1 for v in violations if v["in_diff"])
        skipped = f"; unavailable: {', '.join(sorted({n.split(' ')[0] for n in notes}))}" if notes else ""
        detail = f"{len(violations)} rule violation(s) from MCP linters ({in_diff} inside the diff){skipped}"
        await trace_end(run_id, idx, "SUCCESS", detail, started=started)
    except Exception as exc:  # noqa: BLE001
        await trace_end(run_id, idx, "FAILED", "MCP tool execution failed", str(exc), started)
        notes.append(str(exc)[:300])

    await patch_run(run_id, {"tool_violations": violations[:200]})
    return {"tool_violations": violations, "tool_notes": notes}


def _cosine(a: List[float], b: List[float]) -> float:
    va, vb = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(np.dot(va, vb) / denom) if denom else 0.0


async def rag_node(state: GraphState) -> Dict[str, Any]:
    run_id = state["run_id"]
    started = time.perf_counter()
    idx = await trace_start(run_id, "rag")

    query_parts: List[str] = []
    for f in state.get("code_files", [])[:6]:
        added = set(f.get("added_lines") or [])
        lines = f["content"].split("\n")
        picked = [lines[i - 1] for i in sorted(added)[:60] if 0 < i <= len(lines)] or lines[:60]
        query_parts.append(f"// {f['path']}\n" + "\n".join(picked))
    query = "\n".join(query_parts)[:6000] or "generic source code security review"

    retrieved: List[Dict[str, Any]] = []
    backend = "mongo"
    try:
        vector = await gemini.embed(query)
        remote = await supabase.match_policies(vector, top_k=6)
        if remote:
            backend = "supabase-pgvector"
            retrieved = [{
                "id": str(r["id"]), "title": r["title"], "category": r["category"],
                "cwe": r.get("cwe") or [], "content": r["content"],
                "score": round(float(r.get("similarity", 0)), 4), "backend": backend,
            } for r in remote]
        else:
            docs = await db.policies.find({}, {"_id": 0}).to_list(500)
            scored = [(_cosine(vector, d["embedding"]), d) for d in docs if d.get("embedding")]
            scored.sort(key=lambda x: x[0], reverse=True)
            retrieved = [{
                "id": d["id"], "title": d["title"], "category": d["category"],
                "cwe": d.get("cwe", []), "content": d["content"],
                "score": round(s, 4), "backend": backend,
            } for s, d in scored[:6]]
        detail = f"{len(retrieved)} policy chunk(s) via cosine similarity ({backend})"
        await trace_end(run_id, idx, "SUCCESS", detail, started=started)
    except Exception as exc:  # noqa: BLE001
        docs = await db.policies.find({}, {"_id": 0, "embedding": 0}).limit(6).to_list(6)
        retrieved = [{"id": d["id"], "title": d["title"], "category": d["category"],
                      "cwe": d.get("cwe", []), "content": d["content"], "score": 0.0,
                      "backend": "keyword-fallback"} for d in docs]
        await trace_end(run_id, idx, "FAILED", "embedding unavailable, fell back to unranked corpus",
                        str(exc), started)

    await patch_run(run_id, {"retrieved_policies": retrieved})
    return {"rag_policies": retrieved}


def _build_prompt(state: GraphState) -> str:
    files = state.get("code_files", [])
    allowed: Dict[str, List[int]] = {}
    blocks: List[str] = []
    for f in files:
        added = sorted(set(f.get("added_lines") or []))
        allowed[f["path"]] = added
        blocks.append(
            f"### FILE: {f['path']} ({f['language']})\n"
            f"Commentable (added/changed) lines: {added[:200] if added else 'ALL'}\n"
            "```\n" + diff_utils.numbered_source(f["content"], added) + "\n```"
        )

    tool_lines = []
    for v in state.get("tool_violations", [])[:60]:
        flag = "IN-DIFF" if v.get("in_diff") else "context"
        tool_lines.append(
            f"- [{v['tool']}/{v['rule_id']}] {v['file_path']}:{v['line']} "
            f"sev={v['severity']} cwe={v.get('cwe') or 'n/a'} ({flag}) :: {v['message'][:220]}"
        )
    tools_block = "\n".join(tool_lines) or "- No deterministic linter violations were reported."

    policy_lines = []
    for p in state.get("rag_policies", [])[:6]:
        policy_lines.append(
            f"- [{p['title']}] (score {p['score']}, {', '.join(p.get('cwe', [])) or 'no CWE'})\n  {p['content'][:700]}"
        )
    policies_block = "\n".join(policy_lines) or "- No internal policies retrieved."

    errors = state.get("validation_errors") or []
    correction = ""
    if errors:
        correction = (
            "\n## PREVIOUS ATTEMPT REJECTED BY THE VALIDATOR\n"
            "Your last output failed structural validation. Fix EVERY item below:\n"
            + "\n".join(f"- {e}" for e in errors[:12])
            + "\nRe-emit the complete corrected JSON object.\n"
        )

    return f"""You are the Synthesis Agent of an autonomous pull-request security reviewer.

Your job: merge the DETERMINISTIC linter warnings with the SEMANTIC policy context and emit a
final, actionable inline code review for the pull request in `{state.get('repo_full_name')}`.

## HARD OUTPUT CONTRACT
Return a single JSON object matching the provided schema: summary, risk_score (0-100), comments[].
Every comment MUST anchor to a file_path listed below AND to a line number that appears in that
file's "Commentable lines" list. Never invent a file or a line. Maximum 20 comments.
Deduplicate: one comment per distinct root cause per line.

## WHAT TO REPORT
1. SECURITY: injection, XSS, SSRF, weak crypto, hardcoded secrets, deserialization, access control.
2. LOGIC: off-by-one, inverted conditions, swallowed exceptions, unreachable code, race conditions.
3. MEMORY: unclosed handles, listeners/timers never removed, unbounded caches, leaked subprocesses.
Ignore pure style nits. If a linter finding is a false positive in context, omit it.

## RULES FOR EACH COMMENT
- `rule_id`: reuse the linter rule id when the finding came from a tool, else use LLM-<SHORT-SLUG>.
- `cwe`: the CWE identifier (e.g. CWE-89) when applicable.
- `owasp`: the OWASP Top 10 2021 category when applicable.
- `suggested_code`: the corrected replacement for that line/block ONLY - no surrounding file.
- `policy_citation`: quote the internal policy title you relied on, when one applies.
- `rationale`: explain the concrete exploit or failure mode, not generic advice.

## DETERMINISTIC LINTER VIOLATIONS (MCP: bandit / semgrep / eslint / pattern)
{tools_block}

## RETRIEVED SECURITY POLICIES (pgvector cosine similarity)
{policies_block}

## CHANGED CODE
{chr(10).join(blocks)}
{correction}"""


async def synthesis_node(state: GraphState) -> Dict[str, Any]:
    run_id = state["run_id"]
    attempt = state.get("attempts", 0) + 1
    started = time.perf_counter()
    idx = await trace_start(run_id, "synthesis", attempt)

    prompt = _build_prompt(state)
    before_retries = gemini.retries
    try:
        draft, meta = await gemini.generate_review(prompt)
    except Exception as exc:  # noqa: BLE001
        await trace_end(run_id, idx, "FAILED", "Gemini call failed after retries", str(exc), started)
        return {
            "draft": None, "attempts": attempt,
            "validation_errors": [f"LLM call failed: {str(exc)[:300]}"],
            "llm_usage": [{"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                           "retries": gemini.retries - before_retries}],
        }

    usage = {
        "prompt_tokens": meta["prompt_tokens"],
        "completion_tokens": meta["completion_tokens"],
        "total_tokens": meta["total_tokens"],
        "retries": gemini.retries - before_retries,
    }
    if draft is None:
        await trace_end(run_id, idx, "FAILED", f"attempt {attempt}/{MAX_ATTEMPTS}: malformed JSON",
                        meta.get("parse_error"), started)
        return {"draft": None, "attempts": attempt, "llm_usage": [usage],
                "validation_errors": [f"Pydantic/JSON parse failure: {meta.get('parse_error')}"]}

    detail = f"attempt {attempt}/{MAX_ATTEMPTS}: drafted {len(draft.comments)} comment(s), risk {draft.risk_score}"
    await trace_end(run_id, idx, "SUCCESS", detail, started=started)
    return {"draft": draft.model_dump(), "attempts": attempt, "llm_usage": [usage]}


async def validator_node(state: GraphState) -> Dict[str, Any]:
    run_id = state["run_id"]
    attempt = state.get("attempts", 1)
    started = time.perf_counter()
    idx = await trace_start(run_id, "validator", attempt)

    draft = state.get("draft")
    errors: List[str] = list(state.get("validation_errors") or []) if draft is None else []

    if draft is None:
        await trace_end(run_id, idx, "FAILED",
                        f"attempt {attempt}/{MAX_ATTEMPTS}: no parsable draft to validate",
                        errors[0] if errors else None, started)
        return {"validation_errors": errors or ["Synthesis produced no draft."]}

    allowed: Dict[str, set] = {
        f["path"]: set(f.get("added_lines") or []) for f in state.get("code_files", [])
    }
    line_counts = {f["path"]: len(f["content"].split("\n")) for f in state.get("code_files", [])}

    try:
        model = ReviewDraft.model_validate(draft)
    except Exception as exc:  # noqa: BLE001
        await trace_end(run_id, idx, "FAILED", f"attempt {attempt}/{MAX_ATTEMPTS}: schema violation",
                        str(exc)[:600], started)
        return {"validation_errors": [f"Pydantic schema violation: {str(exc)[:500]}"]}

    kept = []
    for i, c in enumerate(model.comments):
        if c.file_path not in allowed:
            errors.append(f"comments[{i}].file_path '{c.file_path}' is not part of this diff. "
                          f"Valid files: {list(allowed)[:8]}")
            continue
        added = allowed[c.file_path]
        if added and c.line not in added:
            nearest = min(added, key=lambda x: abs(x - c.line)) if added else None
            errors.append(f"comments[{i}] anchors {c.file_path}:{c.line} which is not a changed line. "
                          f"Nearest commentable line is {nearest}.")
            continue
        if not added and c.line > line_counts.get(c.file_path, 0):
            errors.append(f"comments[{i}] line {c.line} exceeds file length "
                          f"{line_counts.get(c.file_path, 0)} in {c.file_path}.")
            continue
        kept.append(c)

    if len(model.comments) > 20:
        errors.append(f"Emitted {len(model.comments)} comments; the contract allows at most 20.")

    if errors:
        await trace_end(run_id, idx, "FAILED",
                        f"attempt {attempt}/{MAX_ATTEMPTS}: {len(errors)} anchor/schema error(s)",
                        " | ".join(errors[:4]), started)
        return {"validation_errors": errors}

    await trace_end(run_id, idx, "SUCCESS",
                    f"attempt {attempt}/{MAX_ATTEMPTS}: {len(kept)} comment(s) passed Pydantic + line-anchor checks",
                    started=started)
    return {"validation_errors": [], "draft": model.model_dump()}


async def finalize_node(state: GraphState) -> Dict[str, Any]:
    run_id = state["run_id"]
    started = time.perf_counter()
    idx = await trace_start(run_id, "finalize")
    draft = state.get("draft") or {}
    n = len(draft.get("comments", []))
    detail = (f"routing {n} inline comment(s) to GitHub + Supabase"
              if state.get("code_files") else "no executable code in this diff - nothing to review")
    await trace_end(run_id, idx, "SUCCESS", detail, started=started)
    return {"status": "COMPLETED"}


async def exhausted_node(state: GraphState) -> Dict[str, Any]:
    run_id = state["run_id"]
    started = time.perf_counter()
    idx = await trace_start(run_id, "exhausted")
    errs = state.get("validation_errors") or []
    await trace_end(run_id, idx, "FAILED",
                    f"self-correction loop exhausted after {MAX_ATTEMPTS} attempts - manual review required",
                    " | ".join(errs[:3]), started)
    return {"status": "FAILED_VALIDATION",
            "error": "Structured output could not be validated in 3 attempts. Manual review required."}


def route_supervisor(state: GraphState):
    return ["tooling", "rag"] if state.get("code_files") else ["finalize"]


def route_validator(state: GraphState) -> str:
    if not state.get("validation_errors"):
        return "finalize"
    if state.get("attempts", 0) < MAX_ATTEMPTS:
        return "synthesis"
    return "exhausted"


def build_graph():
    g = StateGraph(GraphState)
    g.add_node("supervisor", supervisor_node)
    g.add_node("tooling", tooling_node)
    g.add_node("rag", rag_node)
    g.add_node("synthesis", synthesis_node)
    g.add_node("validator", validator_node)
    g.add_node("finalize", finalize_node)
    g.add_node("exhausted", exhausted_node)

    g.add_edge(START, "supervisor")
    g.add_conditional_edges("supervisor", route_supervisor, ["tooling", "rag", "finalize"])
    g.add_edge("tooling", "synthesis")
    g.add_edge("rag", "synthesis")
    g.add_edge("synthesis", "validator")
    g.add_conditional_edges("validator", route_validator, ["synthesis", "finalize", "exhausted"])
    g.add_edge("finalize", END)
    g.add_edge("exhausted", END)
    return g.compile()


GRAPH = build_graph()

GRAPH_TOPOLOGY = [
    {"id": "supervisor", "label": NODE_LABELS["supervisor"], "next": ["tooling", "rag"]},
    {"id": "tooling", "label": NODE_LABELS["tooling"], "next": ["synthesis"]},
    {"id": "rag", "label": NODE_LABELS["rag"], "next": ["synthesis"]},
    {"id": "synthesis", "label": NODE_LABELS["synthesis"], "next": ["validator"]},
    {"id": "validator", "label": NODE_LABELS["validator"], "next": ["finalize", "synthesis", "exhausted"]},
    {"id": "finalize", "label": NODE_LABELS["finalize"], "next": []},
    {"id": "exhausted", "label": NODE_LABELS["exhausted"], "next": []},
]


async def execute_run(run_id: str, repo_full_name: str, files: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run the state machine end to end and persist the outcome."""
    t0 = time.perf_counter()
    state: GraphState = {
        "run_id": run_id, "repo_full_name": repo_full_name, "files": files,
        "attempts": 0, "llm_usage": [], "validation_errors": [], "tool_violations": [],
        "rag_policies": [], "code_files": [], "skipped_files": [],
    }
    await patch_run(run_id, {"status": "RUNNING"})
    try:
        final = await GRAPH.ainvoke(state, config={"recursion_limit": 50})
    except Exception as exc:  # noqa: BLE001
        logger.exception("graph execution failed")
        await patch_run(run_id, {
            "status": "ERROR", "error": str(exc)[:800],
            "completed_at": _now(), "latency_ms": int((time.perf_counter() - t0) * 1000),
        })
        doc = await db.runs.find_one({"id": run_id}, {"_id": 0})
        return doc

    usage = final.get("llm_usage", [])
    prompt_tokens = sum(u["prompt_tokens"] for u in usage)
    completion_tokens = sum(u["completion_tokens"] for u in usage)
    draft = final.get("draft") or {}
    valid = not final.get("validation_errors")
    status = final.get("status") or ("COMPLETED" if valid else "FAILED_VALIDATION")

    metrics = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": sum(u["total_tokens"] for u in usage) or (prompt_tokens + completion_tokens),
        "estimated_cost_usd": estimate_cost(prompt_tokens, completion_tokens),
        "llm_calls": len(usage),
        "llm_retries": sum(u.get("retries", 0) for u in usage),
        "validation_attempts": final.get("attempts", 0),
        "tool_violations": len(final.get("tool_violations", [])),
        "policies_retrieved": len(final.get("rag_policies", [])),
    }

    changed = [{
        "path": f["path"], "language": f.get("language", "other"),
        "added_lines": f.get("added_lines", []), "patch": f.get("patch", "")[:20000],
        "content": f.get("content", "")[:40000], "skipped_reason": f.get("skipped_reason"),
    } for f in final.get("code_files", []) + final.get("skipped_files", [])]

    patch = {
        "status": status,
        "summary": draft.get("summary", "") if valid else (final.get("error") or "Validation failed."),
        "risk_score": draft.get("risk_score", 0) if valid else 0,
        "findings": draft.get("comments", []) if valid else [],
        "validation_errors": final.get("validation_errors", []),
        "metrics": metrics,
        "changed_files": changed,
        "error": final.get("error"),
        "completed_at": _now(),
        "latency_ms": int((time.perf_counter() - t0) * 1000),
    }
    await patch_run(run_id, patch)

    doc = await db.runs.find_one({"id": run_id}, {"_id": 0})
    if doc:
        asyncio.create_task(_mirror(doc))
    return doc


async def _mirror(doc: Dict[str, Any]):
    try:
        await supabase.mirror_run(doc)
    except Exception:  # noqa: BLE001
        logger.warning("supabase mirror failed", exc_info=False)
