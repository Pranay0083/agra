"""Backend tests for Autonomous PR Security Reviewer.

Covers: system health, samples, review simulate (python + node),
validator rejects unsupported extensions, line-anchor enforcement,
webhook HMAC + idempotency, reviews CRUD, publish rejected for simulation,
policies CRUD + RAG search, analytics, supabase bootstrap SQL.
"""
import hashlib
import hmac
import json
import os
import time
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")).rstrip("/")

backend_env = dotenv_values("/app/backend/.env")
WEBHOOK_SECRET = backend_env.get("GITHUB_WEBHOOK_SECRET", "Xq7mPvR2tKdN8wLzB4hYgJ6sTcUeA1nF")

POLL_TIMEOUT_S = 180
POLL_INTERVAL_S = 3


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _poll_run(client, run_id, timeout=POLL_TIMEOUT_S):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = client.get(f"{BASE_URL}/api/reviews/{run_id}")
        assert r.status_code == 200, r.text
        last = r.json()
        if last["status"] in ("COMPLETED", "FAILED_VALIDATION", "ERROR"):
            return last
        time.sleep(POLL_INTERVAL_S)
    pytest.fail(f"Run {run_id} did not finish in {timeout}s (last status={last and last.get('status')})")


# ---------- system health & samples ----------
class TestSystem:
    def test_health(self, client):
        r = client.get(f"{BASE_URL}/api/system/health")
        assert r.status_code == 200
        d = r.json()
        assert d["gemini"]["ok"] is True
        assert d["github"]["ok"] is True and d["github"]["login"] == "AgrapujyaLashkari"
        assert d["supabase"]["ready"] is True and d["supabase"]["pgvector"] is True
        assert d["mongo"]["ok"] is True
        for k in ("bandit_scan", "semgrep_scan", "eslint_scan", "pattern_scan"):
            assert d["linters"][k] is True, f"linter {k} not ready"
        assert d["rag"]["embedded"] > 0

    def test_samples(self, client):
        r = client.get(f"{BASE_URL}/api/samples")
        assert r.status_code == 200
        ids = {s["id"] for s in r.json()["samples"]}
        assert {"python-flask", "node-express"}.issubset(ids)

    def test_supabase_bootstrap_sql(self, client):
        r = client.get(f"{BASE_URL}/api/system/supabase-sql")
        assert r.status_code == 200
        text = r.text if "sql" not in r.headers.get("content-type", "") else r.text
        try:
            body = r.json()
            sql = body.get("sql") or body.get("bootstrap_sql") or json.dumps(body)
        except Exception:
            sql = text
        assert "create extension if not exists vector" in sql.lower()
        assert "match_security_policies" in sql


# ---------- review simulate ----------
class TestSimulate:
    _created = []

    @classmethod
    def teardown_class(cls):
        s = requests.Session()
        for rid in cls._created:
            try:
                s.delete(f"{BASE_URL}/api/reviews/{rid}")
            except Exception:
                pass

    def _get_sample(self, client, sid):
        r = client.get(f"{BASE_URL}/api/samples")
        for s in r.json()["samples"]:
            if s["id"] == sid:
                return s
        pytest.fail(f"sample {sid} not found")

    def test_simulate_python_flask(self, client):
        sample = self._get_sample(client, "python-flask")
        r = client.post(f"{BASE_URL}/api/reviews/simulate", json={
            "repo_full_name": "TEST_local/sandbox",
            "pr_title": "TEST py",
            "file_path": sample["file_path"],
            "content": sample["content"],
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "QUEUED" and d["run_id"]
        run_id = d["run_id"]
        self.__class__._created.append(run_id)
        run = _poll_run(client, run_id)
        assert run["status"] == "COMPLETED", f"status={run['status']} error={run.get('error')}"

        # trace nodes SUCCESS
        trace = {t["node"]: t for t in run["trace"]}
        for node in ("supervisor", "tooling", "rag", "synthesis", "validator", "finalize"):
            assert node in trace, f"trace missing {node}"
            assert trace[node]["status"] == "SUCCESS", f"node {node} not SUCCESS: {trace[node]}"

        # tool violations from at least two distinct tools including bandit + semgrep
        tools = {v["tool"] for v in run["tool_violations"]}
        assert "bandit" in tools and "semgrep" in tools, f"tools present: {tools}"

        # retrieved policies with supabase-pgvector backend and non-zero scores
        assert run["retrieved_policies"], "no policies retrieved"
        assert any(p["backend"] == "supabase-pgvector" for p in run["retrieved_policies"])
        assert all(p["score"] > 0 for p in run["retrieved_policies"])

        # findings with severity/cwe/suggested_code
        assert run["findings"], "no findings produced"
        assert any(f.get("cwe") for f in run["findings"])
        assert any(f.get("suggested_code") for f in run["findings"])
        for f in run["findings"]:
            assert f["severity"] in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")

        # metrics + validation attempts
        assert run["metrics"]["total_tokens"] > 0
        assert run["metrics"]["estimated_cost_usd"] > 0
        assert run["metrics"]["validation_attempts"] <= 3

        # line anchor: every finding.file_path == submitted and line <= line count
        line_count = len(sample["content"].splitlines())
        for f in run["findings"]:
            assert f["file_path"] == sample["file_path"]
            assert 1 <= f["line"] <= line_count, f"finding line {f['line']} out of range 1..{line_count}"

    def test_simulate_node_express(self, client):
        sample = self._get_sample(client, "node-express")
        r = client.post(f"{BASE_URL}/api/reviews/simulate", json={
            "repo_full_name": "TEST_local/sandbox",
            "pr_title": "TEST js",
            "file_path": sample["file_path"],
            "content": sample["content"],
        })
        assert r.status_code == 200, r.text
        run_id = r.json()["run_id"]
        self.__class__._created.append(run_id)
        run = _poll_run(client, run_id)
        assert run["status"] == "COMPLETED", f"status={run['status']} error={run.get('error')}"
        tools = {v["tool"] for v in run["tool_violations"]}
        assert tools & {"eslint", "pattern"}, f"expected eslint/pattern for JS, got {tools}"

    def test_simulate_rejects_markdown(self, client):
        r = client.post(f"{BASE_URL}/api/reviews/simulate", json={
            "file_path": "README.md",
            "content": "# hi\nsome markdown text\n",
        })
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text[:300]}"

    def test_publish_rejects_simulation(self, client):
        # create a quick simulation and try publishing it
        sample = self._get_sample(client, "python-flask")
        r = client.post(f"{BASE_URL}/api/reviews/simulate", json={
            "file_path": sample["file_path"],
            "content": sample["content"],
        })
        run_id = r.json()["run_id"]
        self.__class__._created.append(run_id)
        _poll_run(client, run_id)
        pub = client.post(f"{BASE_URL}/api/reviews/{run_id}/publish")
        assert pub.status_code == 400, f"expected 400, got {pub.status_code}: {pub.text[:300]}"


# ---------- webhook ----------
def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


class TestWebhook:
    def test_ping_ok(self, client):
        body = json.dumps({"zen": "hi"}).encode()
        r = requests.post(
            f"{BASE_URL}/api/webhooks/github",
            data=body,
            headers={
                "X-GitHub-Event": "ping",
                "X-GitHub-Delivery": str(uuid.uuid4()),
                "X-Hub-Signature-256": _sign(body),
                "Content-Type": "application/json",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json().get("pong") is True

    def test_missing_signature_forbidden(self, client):
        r = requests.post(
            f"{BASE_URL}/api/webhooks/github",
            data=b"{}",
            headers={"X-GitHub-Event": "ping", "Content-Type": "application/json"},
        )
        assert r.status_code == 403

    def test_tampered_body_forbidden(self, client):
        body = json.dumps({"zen": "hi"}).encode()
        sig = _sign(body)
        r = requests.post(
            f"{BASE_URL}/api/webhooks/github",
            data=body + b"tamper",
            headers={
                "X-GitHub-Event": "ping",
                "X-Hub-Signature-256": sig,
                "Content-Type": "application/json",
            },
        )
        assert r.status_code == 403

    def test_pull_request_closed_ignored(self, client):
        payload = {"action": "closed", "number": 1, "repository": {"full_name": "x/y"}, "pull_request": {"number": 1}}
        body = json.dumps(payload).encode()
        r = requests.post(
            f"{BASE_URL}/api/webhooks/github",
            data=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": str(uuid.uuid4()),
                "X-Hub-Signature-256": _sign(body),
                "Content-Type": "application/json",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json().get("ignored") is True

    def test_pull_request_opened_idempotent(self, client):
        delivery = str(uuid.uuid4())
        payload = {
            "action": "opened",
            "number": 999999,
            "repository": {"full_name": "TEST_nonexistent_org/TEST_nonexistent_repo", "owner": {"login": "TEST_nonexistent_org"}, "name": "TEST_nonexistent_repo"},
            "pull_request": {"number": 999999, "title": "TEST", "user": {"login": "TEST"}, "head": {"sha": "deadbeef"}, "html_url": ""},
        }
        body = json.dumps(payload).encode()
        headers = {
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": delivery,
            "X-Hub-Signature-256": _sign(body),
            "Content-Type": "application/json",
        }
        r1 = requests.post(f"{BASE_URL}/api/webhooks/github", data=body, headers=headers)
        r2 = requests.post(f"{BASE_URL}/api/webhooks/github", data=body, headers=headers)
        assert r1.status_code == 200, r1.text
        assert r2.status_code == 200, r2.text
        assert r2.json().get("duplicate") is True, f"second delivery not deduped: {r2.json()}"


# ---------- reviews list / get / delete ----------
class TestReviewsCrud:
    def test_list_and_status_filter(self, client):
        r = client.get(f"{BASE_URL}/api/reviews")
        assert r.status_code == 200
        assert isinstance(r.json(), (list, dict))
        r2 = client.get(f"{BASE_URL}/api/reviews", params={"status": "COMPLETED"})
        assert r2.status_code == 200

    def test_get_missing_returns_404(self, client):
        r = client.get(f"{BASE_URL}/api/reviews/does-not-exist-{uuid.uuid4()}")
        assert r.status_code == 404

    def test_delete_missing_returns_404(self, client):
        r = client.delete(f"{BASE_URL}/api/reviews/does-not-exist-{uuid.uuid4()}")
        assert r.status_code == 404


# ---------- policies + RAG ----------
class TestPolicies:
    _created_ids = []

    @classmethod
    def teardown_class(cls):
        for pid in cls._created_ids:
            try:
                requests.delete(f"{BASE_URL}/api/policies/{pid}")
            except Exception:
                pass

    def test_list_builtin(self, client):
        r = client.get(f"{BASE_URL}/api/policies")
        assert r.status_code == 200
        d = r.json()
        items = d if isinstance(d, list) else d.get("policies") or d.get("items") or []
        builtins = [p for p in items if p.get("source", "builtin") == "builtin"]
        assert len(builtins) >= 15, f"expected 15 builtin policies, got {len(builtins)}"

    def test_create_and_delete(self, client):
        payload = {
            "title": "TEST_Custom SQLi Policy",
            "category": "CUSTOM",
            "cwe": ["CWE-89"],
            "content": "Custom SQL injection policy content used for TEST_ automated verification.",
        }
        r = client.post(f"{BASE_URL}/api/policies", json=payload)
        assert r.status_code in (200, 201), r.text
        p = r.json()
        pid = p.get("id") or p.get("policy", {}).get("id")
        assert pid, f"no id in create response: {p}"
        self.__class__._created_ids.append(pid)
        # verify listing includes it
        lst = client.get(f"{BASE_URL}/api/policies").json()
        items = lst if isinstance(lst, list) else lst.get("policies") or lst.get("items") or []
        assert any((x.get("id") == pid) for x in items)
        # delete
        d = client.delete(f"{BASE_URL}/api/policies/{pid}")
        assert d.status_code in (200, 204)
        self.__class__._created_ids.remove(pid)

    def test_search_sqli(self, client):
        r = client.post(f"{BASE_URL}/api/policies/search", json={"query": "SQL injection via string concatenation in a query"})
        assert r.status_code == 200, r.text
        d = r.json()
        results = d.get("results") or d.get("policies") or d
        backend = d.get("backend") or (results[0].get("backend") if results else None)
        assert backend == "supabase-pgvector", f"backend={backend}"
        assert len(results) == 5
        top_text = (results[0].get("title", "") + " " + results[0].get("content", "")).lower()
        assert "sql" in top_text or "injection" in top_text, f"top hit not SQL/injection: {results[0].get('title')}"


# ---------- analytics ----------
class TestAnalytics:
    def test_overview(self, client):
        r = client.get(f"{BASE_URL}/api/analytics/overview")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("total_runs", "severity", "top_cwe", "tool_attribution", "timeline", "cost", "latency", "resilience"):
            assert key in d, f"missing {key} in analytics: {list(d.keys())}"
        tools = d["tool_attribution"]
        # tool_attribution may be dict or list; extract labels
        if isinstance(tools, dict):
            labels = set(tools.keys())
        else:
            labels = {(t.get("tool") or t.get("name") or "").lower() for t in tools}
        # must include the deterministic tools
        assert {"bandit", "semgrep", "pattern"}.issubset({l.lower() for l in labels}), f"tool_attribution labels={labels}"
        # must NOT mis-attribute python semgrep rules to eslint - simple sanity: eslint count 0 or JS-only.
        # We cannot fully verify attribution here without run context; we just assert labels look sane.
