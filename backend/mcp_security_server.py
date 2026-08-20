#!/usr/bin/env python3
"""MCP (Model Context Protocol) stdio server exposing security linters as tools.

Speaks JSON-RPC 2.0 over newline-delimited stdin/stdout. Every tool executes its
linter inside a throwaway temp directory with a stripped environment and a hard
wall-clock timeout, so untrusted PR code is never run - only statically parsed.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

PROTOCOL_VERSION = "2024-11-05"
RULES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "semgrep_rules", "security.yaml")
TIMEOUT = 45

_BIN = os.path.dirname(sys.executable)
_PATH = os.pathsep.join(filter(None, [
    _BIN, os.environ.get("PATH", ""),
    "/root/.venv/bin", "/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin", "/sbin", "/bin",
]))
SANDBOX_ENV = {
    "PATH": _PATH,
    "HOME": "/tmp",
    "LANG": "C.UTF-8",
    "SEMGREP_SEND_METRICS": "off",
    "SEMGREP_ENABLE_VERSION_CHECK": "0",
    "PYTHONDONTWRITEBYTECODE": "1",
}


def _which(binary: str):
    return shutil.which(binary, path=_PATH)

BANDIT_SEV = {"HIGH": "HIGH", "MEDIUM": "MEDIUM", "LOW": "LOW"}
SEMGREP_SEV = {"ERROR": "HIGH", "WARNING": "MEDIUM", "INFO": "LOW"}

JS_PATTERNS = [
    ("JS-SEC-001", r"\beval\s*\(", "HIGH", "CWE-95", "eval() executes arbitrary JavaScript from a string."),
    ("JS-SEC-002", r"new\s+Function\s*\(", "HIGH", "CWE-95", "new Function() compiles arbitrary code at runtime."),
    ("JS-SEC-003", r"\.innerHTML\s*=", "MEDIUM", "CWE-79", "innerHTML assignment can introduce DOM XSS."),
    ("JS-SEC-004", r"dangerouslySetInnerHTML", "MEDIUM", "CWE-79", "dangerouslySetInnerHTML bypasses React escaping."),
    ("JS-SEC-005", r"child_process\s*\.\s*exec(Sync)?\s*\(", "HIGH", "CWE-78", "child_process.exec invokes a shell - command injection risk."),
    ("JS-SEC-006", r"(api[_-]?key|secret|password|token)\s*[:=]\s*[\"'][A-Za-z0-9_\-]{12,}[\"']", "HIGH", "CWE-798", "Hardcoded credential detected in source."),
    ("JS-SEC-007", r"createHash\s*\(\s*[\"'](md5|sha1)[\"']\s*\)", "MEDIUM", "CWE-327", "MD5/SHA1 are broken for security purposes."),
    ("JS-SEC-008", r"Math\.random\s*\(\s*\)", "LOW", "CWE-338", "Math.random() is not cryptographically secure."),
    ("JS-SEC-009", r"rejectUnauthorized\s*:\s*false", "HIGH", "CWE-295", "TLS certificate validation disabled."),
    ("JS-SEC-010", r"document\.write\s*\(", "MEDIUM", "CWE-79", "document.write can inject unescaped markup."),
    ("JS-MEM-001", r"\bsetInterval\s*\(", "LOW", "CWE-401", "setInterval without a matching clearInterval leaks timers."),
    ("JS-MEM-002", r"addEventListener\s*\(", "INFO", "CWE-401", "Listener added - verify a matching removeEventListener on teardown."),
    ("JS-LOGIC-001", r"==\s*(null|undefined)\b", "LOW", "CWE-480", "Loose equality against null/undefined - prefer ===."),
    ("JS-LOGIC-002", r"catch\s*\([^)]*\)\s*\{\s*\}", "MEDIUM", "CWE-390", "Empty catch block silently swallows errors."),
    ("JS-SEC-011", r"process\.env\.[A-Z_]+\s*\|\|\s*[\"'][^\"']{8,}[\"']", "MEDIUM", "CWE-798", "Fallback secret hardcoded next to env lookup."),
]

PY_EXTRA_PATTERNS = [
    ("PY-MEM-001", r"^\s*global\s+\w+", "LOW", "CWE-401", "Module-level mutable global can grow unbounded."),
    ("PY-LOGIC-001", r"except\s*:\s*$", "MEDIUM", "CWE-396", "Bare except swallows every error including KeyboardInterrupt."),
    ("PY-LOGIC-002", r"except\s+Exception\s*:\s*\n\s*pass", "MEDIUM", "CWE-390", "Exception silently ignored."),
    ("PY-MEM-002", r"open\s*\([^)]*\)\s*\.\s*read\s*\(\s*\)", "LOW", "CWE-772", "File handle opened without a context manager is never closed."),
]


def _write(sandbox: str, filename: str, content: str) -> str:
    safe = os.path.basename(filename) or "snippet.txt"
    path = os.path.join(sandbox, safe)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path


def _run(cmd, cwd):
    return subprocess.run(
        cmd, cwd=cwd, env=SANDBOX_ENV, capture_output=True, text=True, timeout=TIMEOUT
    )


def bandit_scan(filename: str, content: str):
    if not _which("bandit"):
        return {"tool": "bandit", "available": False, "violations": [], "raw": "bandit binary not found"}
    with tempfile.TemporaryDirectory(prefix="mcp-bandit-") as sandbox:
        target = _write(sandbox, filename, content)
        try:
            proc = _run(["bandit", "-f", "json", "-q", "-ll", os.path.basename(target)], sandbox)
        except subprocess.TimeoutExpired:
            return {"tool": "bandit", "available": True, "violations": [], "raw": "timeout"}
        violations = []
        try:
            data = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError:
            data = {}
        for item in data.get("results", []):
            violations.append({
                "tool": "bandit",
                "rule_id": item.get("test_id", "B000"),
                "file_path": filename,
                "line": item.get("line_number", 1),
                "severity": BANDIT_SEV.get(item.get("issue_severity", "MEDIUM"), "MEDIUM"),
                "confidence": item.get("issue_confidence", "MEDIUM"),
                "message": f"{item.get('test_name', '')}: {item.get('issue_text', '')}".strip(": "),
                "cwe": (item.get("issue_cwe") or {}).get("id") and f"CWE-{item['issue_cwe']['id']}" or None,
                "snippet": (item.get("code") or "").strip()[:400],
            })
        return {"tool": "bandit", "available": True, "violations": violations, "raw": (proc.stderr or "")[:2000]}


def semgrep_scan(filename: str, content: str):
    if not _which("semgrep"):
        return {"tool": "semgrep", "available": False, "violations": [], "raw": "semgrep binary not found"}
    with tempfile.TemporaryDirectory(prefix="mcp-semgrep-") as sandbox:
        target = _write(sandbox, filename, content)
        cmd = [
            "semgrep", "scan", "--config", RULES_FILE, "--json", "--quiet",
            "--metrics", "off", "--disable-version-check", "--no-git-ignore",
            os.path.basename(target),
        ]
        try:
            proc = _run(cmd, sandbox)
        except subprocess.TimeoutExpired:
            return {"tool": "semgrep", "available": True, "violations": [], "raw": "timeout"}
        violations = []
        try:
            data = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError:
            data = {}
        for item in data.get("results", []):
            extra = item.get("extra", {})
            meta = extra.get("metadata", {})
            violations.append({
                "tool": "semgrep",
                "rule_id": item.get("check_id", "semgrep.rule").split(".")[-1],
                "file_path": filename,
                "line": item.get("start", {}).get("line", 1),
                "severity": SEMGREP_SEV.get(extra.get("severity", "WARNING"), "MEDIUM"),
                "confidence": "HIGH",
                "message": extra.get("message", "").strip(),
                "cwe": meta.get("cwe"),
                "snippet": (extra.get("lines") or "").strip()[:400],
            })
        return {"tool": "semgrep", "available": True, "violations": violations, "raw": (proc.stderr or "")[:2000]}


def eslint_scan(filename: str, content: str):
    if not _which("eslint"):
        return {"tool": "eslint", "available": False, "violations": [], "raw": "eslint binary not found"}
    with tempfile.TemporaryDirectory(prefix="mcp-eslint-") as sandbox:
        target = _write(sandbox, filename if filename.endswith((".js", ".jsx", ".mjs", ".cjs")) else "snippet.js", content)
        with open(os.path.join(sandbox, "eslint.config.mjs"), "w", encoding="utf-8") as fh:
            fh.write(
                "export default [{\n"
                "  languageOptions: { ecmaVersion: 'latest', sourceType: 'module',\n"
                "    globals: { window: 'readonly', document: 'readonly', console: 'readonly',\n"
                "      process: 'readonly', require: 'readonly', module: 'writable', exports: 'writable',\n"
                "      Buffer: 'readonly', __dirname: 'readonly', fetch: 'readonly', localStorage: 'readonly',\n"
                "      setTimeout: 'readonly', setInterval: 'readonly', clearTimeout: 'readonly',\n"
                "      clearInterval: 'readonly', URL: 'readonly', crypto: 'readonly' } },\n"
                "  rules: {\n"
                "    'no-eval': 'error',\n"
                "    'no-implied-eval': 'error',\n"
                "    'no-new-func': 'error',\n"
                "    'no-unused-vars': 'warn',\n"
                "    'no-undef': 'warn',\n"
                "    'no-empty': 'warn',\n"
                "    'eqeqeq': 'warn',\n"
                "    'no-fallthrough': 'error',\n"
                "    'no-self-assign': 'error',\n"
                "    'no-unreachable': 'error',\n"
                "    'require-atomic-updates': 'warn'\n"
                "  }\n"
                "}];\n"
            )
        try:
            proc = _run(["eslint", "--no-color", "-f", "json", os.path.basename(target)], sandbox)
        except subprocess.TimeoutExpired:
            return {"tool": "eslint", "available": True, "violations": [], "raw": "timeout"}
        violations = []
        try:
            data = json.loads(proc.stdout or "[]")
        except json.JSONDecodeError:
            data = []
        for f in data:
            for m in f.get("messages", []):
                violations.append({
                    "tool": "eslint",
                    "rule_id": m.get("ruleId") or "parse-error",
                    "file_path": filename,
                    "line": m.get("line", 1),
                    "severity": "HIGH" if m.get("severity") == 2 else "LOW",
                    "confidence": "HIGH",
                    "message": m.get("message", ""),
                    "cwe": None,
                    "snippet": None,
                })
        return {"tool": "eslint", "available": True, "violations": violations, "raw": (proc.stderr or "")[:1500]}


def pattern_scan(filename: str, content: str):
    lower = filename.lower()
    rules = JS_PATTERNS if lower.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")) else PY_EXTRA_PATTERNS
    violations = []
    lines = content.split("\n")
    for rule_id, pattern, severity, cwe, message in rules:
        rx = re.compile(pattern, re.MULTILINE)
        for idx, line in enumerate(lines, start=1):
            if rx.search(line):
                violations.append({
                    "tool": "pattern",
                    "rule_id": rule_id,
                    "file_path": filename,
                    "line": idx,
                    "severity": severity,
                    "confidence": "MEDIUM",
                    "message": message,
                    "cwe": cwe,
                    "snippet": line.strip()[:300],
                })
    return {"tool": "pattern", "available": True, "violations": violations, "raw": ""}


TOOLS = {
    "bandit_scan": {
        "handler": bandit_scan,
        "description": "Run the Bandit static security analyzer against a Python source file.",
    },
    "semgrep_scan": {
        "handler": semgrep_scan,
        "description": "Run Semgrep with the local OWASP/CWE ruleset against Python or JavaScript source.",
    },
    "eslint_scan": {
        "handler": eslint_scan,
        "description": "Run ESLint with a security-oriented rule set against JavaScript source.",
    },
    "pattern_scan": {
        "handler": pattern_scan,
        "description": "Run built-in regex rules for JS/Python security, logic and memory-leak smells.",
    },
}

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "filename": {"type": "string"},
        "content": {"type": "string"},
    },
    "required": ["filename", "content"],
}


def handle(msg):
    method = msg.get("method")
    mid = msg.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": mid,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "security-linters", "version": "1.0.0"},
            },
        }
    if method == "tools/list":
        return {
            "jsonrpc": "2.0", "id": mid,
            "result": {
                "tools": [
                    {"name": name, "description": meta["description"], "inputSchema": INPUT_SCHEMA}
                    for name, meta in TOOLS.items()
                ]
            },
        }
    if method == "tools/call":
        params = msg.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})
        tool = TOOLS.get(name)
        if tool is None:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Unknown tool {name}"}}
        try:
            payload = tool["handler"](args.get("filename", "snippet.txt"), args.get("content", ""))
            return {
                "jsonrpc": "2.0", "id": mid,
                "result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False},
            }
        except Exception as exc:  # noqa: BLE001 - surface tool crash to the agent
            return {
                "jsonrpc": "2.0", "id": mid,
                "result": {"content": [{"type": "text", "text": json.dumps({"tool": name, "available": True, "violations": [], "raw": str(exc)[:800]})}], "isError": True},
            }
    if method and method.startswith("notifications/"):
        return None
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Unknown method {method}"}}


def main():
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue
        response = handle(msg)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
