"""GitHub REST client: webhook HMAC verification, PR diff retrieval, inline review posting."""
import hashlib
import hmac
import logging
from typing import Any, Dict, List, Optional

import httpx

import config

logger = logging.getLogger(__name__)

GH_API = "https://api.github.com"
API_VERSION = "2022-11-28"


def verify_signature(body: bytes, signature: Optional[str]) -> bool:
    secret = config.GITHUB_WEBHOOK_SECRET
    if not secret:
        return False
    if not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _headers(accept: str = "application/vnd.github+json") -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {config.GITHUB_TOKEN}",
        "Accept": accept,
        "X-GitHub-Api-Version": API_VERSION,
    }


class GitHubClient:
    @property
    def configured(self) -> bool:
        return bool(config.GITHUB_TOKEN)

    async def whoami(self) -> Dict[str, Any]:
        if not self.configured:
            return {"ok": False, "detail": "GITHUB_TOKEN missing"}
        try:
            async with httpx.AsyncClient(timeout=20.0) as c:
                r = await c.get(f"{GH_API}/user", headers=_headers())
            if r.status_code == 200:
                data = r.json()
                return {"ok": True, "login": data.get("login"), "avatar_url": data.get("avatar_url")}
            return {"ok": False, "detail": f"{r.status_code}: {r.text[:200]}"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "detail": str(exc)[:200]}

    async def get_pull(self, owner: str, repo: str, number: int) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.get(f"{GH_API}/repos/{owner}/{repo}/pulls/{number}", headers=_headers())
        if r.status_code >= 400:
            raise ValueError(f"GitHub {r.status_code}: {r.text[:300]}")
        return r.json()

    async def list_files(self, owner: str, repo: str, number: int) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        page = 1
        async with httpx.AsyncClient(timeout=40.0) as c:
            while True:
                r = await c.get(
                    f"{GH_API}/repos/{owner}/{repo}/pulls/{number}/files",
                    headers=_headers(), params={"per_page": 100, "page": page},
                )
                if r.status_code >= 400:
                    raise ValueError(f"GitHub {r.status_code}: {r.text[:300]}")
                batch = r.json()
                items.extend(batch)
                if len(batch) < 100:
                    return items
                page += 1

    async def get_file_content(self, owner: str, repo: str, path: str, ref: str) -> str:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as c:
            r = await c.get(
                f"{GH_API}/repos/{owner}/{repo}/contents/{path}",
                headers=_headers("application/vnd.github.raw"), params={"ref": ref},
            )
        if r.status_code >= 400:
            return ""
        return r.text

    async def post_review(self, owner: str, repo: str, number: int, commit_id: str,
                          body: str, comments: List[Dict[str, Any]]) -> Dict[str, Any]:
        payload = {
            "commit_id": commit_id,
            "body": body,
            "event": "COMMENT",
            "comments": comments,
        }
        async with httpx.AsyncClient(timeout=45.0) as c:
            r = await c.post(f"{GH_API}/repos/{owner}/{repo}/pulls/{number}/reviews",
                             headers=_headers(), json=payload)
        if r.status_code >= 400:
            # Fall back to a summary-only review when inline anchors are rejected.
            if comments:
                async with httpx.AsyncClient(timeout=45.0) as c2:
                    r2 = await c2.post(
                        f"{GH_API}/repos/{owner}/{repo}/pulls/{number}/reviews",
                        headers=_headers(),
                        json={"commit_id": commit_id, "body": body, "event": "COMMENT"},
                    )
                if r2.status_code < 400:
                    out = r2.json()
                    out["_degraded"] = f"inline anchors rejected ({r.status_code}); posted summary only"
                    return out
            raise ValueError(f"GitHub {r.status_code}: {r.text[:400]}")
        return r.json()


github = GitHubClient()
