"""Minimal MCP stdio client: spawns the security-linter MCP server per session."""
import asyncio
import json
import os
import sys
from typing import Any, Dict, List

SERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_security_server.py")


class MCPSession:
    def __init__(self):
        self.proc = None
        self._id = 0

    async def __aenter__(self):
        self.proc = await asyncio.create_subprocess_exec(
            sys.executable, SERVER,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await self.request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "pr-security-reviewer", "version": "1.0.0"},
        })
        return self

    async def __aexit__(self, *_):
        if self.proc and self.proc.returncode is None:
            try:
                self.proc.stdin.close()
            except Exception:
                pass
            try:
                await asyncio.wait_for(self.proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.proc.kill()

    async def request(self, method: str, params: Dict[str, Any], timeout: int = 90) -> Dict[str, Any]:
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        self.proc.stdin.write((json.dumps(payload) + "\n").encode())
        await self.proc.stdin.drain()
        line = await asyncio.wait_for(self.proc.stdout.readline(), timeout=timeout)
        if not line:
            raise RuntimeError("MCP server closed the connection")
        return json.loads(line.decode())

    async def list_tools(self) -> List[str]:
        res = await self.request("tools/list", {})
        return [t["name"] for t in res.get("result", {}).get("tools", [])]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        res = await self.request("tools/call", {"name": name, "arguments": arguments})
        result = res.get("result") or {}
        content = result.get("content") or []
        if not content:
            return {"tool": name, "available": False, "violations": [], "raw": json.dumps(res.get("error", {}))}
        return json.loads(content[0]["text"])


async def probe_tools() -> Dict[str, bool]:
    """Health check: which linters are actually installed in the sandbox."""
    probes = {
        "bandit_scan": ("probe.py", "import os\nos.system('ls')\n"),
        "semgrep_scan": ("probe.py", "import os\nos.system('ls')\n"),
        "eslint_scan": ("probe.js", "var a = 1;\n"),
        "pattern_scan": ("probe.js", "eval('1');\n"),
    }
    out: Dict[str, bool] = {}
    try:
        async with MCPSession() as session:
            names = await session.list_tools()
            for name in names:
                fname, code = probes.get(name, ("probe.py", "x = 1\n"))
                try:
                    res = await session.call_tool(name, {"filename": fname, "content": code})
                    out[name] = bool(res.get("available"))
                except Exception:
                    out[name] = False
    except Exception:
        return {k: False for k in probes}
    return out
