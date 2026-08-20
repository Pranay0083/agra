import re
from typing import Dict, List

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

LANG_BY_EXT = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "javascript",
    ".tsx": "javascript",
}

SKIP_EXT = {
    ".md", ".markdown", ".txt", ".rst", ".json", ".yaml", ".yml", ".toml",
    ".ini", ".cfg", ".lock", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico",
    ".webp", ".csv", ".html", ".css", ".scss", ".xml",
}


def detect_language(path: str) -> str:
    lower = path.lower()
    for ext, lang in LANG_BY_EXT.items():
        if lower.endswith(ext):
            return lang
    for ext in SKIP_EXT:
        if lower.endswith(ext):
            return "docs"
    return "other"


def parse_patch(patch: str) -> Dict:
    """Parse a unified diff patch into hunks with new-file line numbers."""
    hunks: List[Dict] = []
    added: List[int] = []
    removed: List[int] = []
    if not patch:
        return {"hunks": [], "added_lines": [], "removed_lines": []}

    new_ln = 0
    old_ln = 0
    current = None
    for raw in patch.split("\n"):
        m = HUNK_RE.match(raw)
        if m:
            old_ln = int(m.group(1))
            new_ln = int(m.group(3))
            current = {"header": raw, "new_start": new_ln, "lines": []}
            hunks.append(current)
            continue
        if current is None:
            continue
        if raw.startswith("+"):
            current["lines"].append({"type": "add", "new_line": new_ln, "old_line": None, "content": raw[1:]})
            added.append(new_ln)
            new_ln += 1
        elif raw.startswith("-"):
            current["lines"].append({"type": "del", "new_line": None, "old_line": old_ln, "content": raw[1:]})
            removed.append(old_ln)
            old_ln += 1
        elif raw.startswith("\\"):
            continue
        else:
            current["lines"].append({"type": "ctx", "new_line": new_ln, "old_line": old_ln, "content": raw[1:] if raw else ""})
            new_ln += 1
            old_ln += 1
    return {"hunks": hunks, "added_lines": added, "removed_lines": removed}


def synth_full_add_patch(content: str) -> str:
    """Build a synthetic unified diff where every line is an addition."""
    lines = content.split("\n")
    body = "\n".join("+" + ln for ln in lines)
    return f"@@ -0,0 +1,{len(lines)} @@\n{body}"


def snippet_around(content: str, line: int, radius: int = 3) -> str:
    lines = content.split("\n")
    start = max(0, line - 1 - radius)
    end = min(len(lines), line + radius)
    out = []
    for i in range(start, end):
        marker = ">>" if i == line - 1 else "  "
        out.append(f"{marker} {i + 1:>4} | {lines[i]}")
    return "\n".join(out)


def numbered_source(content: str, added: List[int], limit: int = 900) -> str:
    lines = content.split("\n")[:limit]
    added_set = set(added)
    out = []
    for i, ln in enumerate(lines, start=1):
        flag = "+" if i in added_set else " "
        out.append(f"{flag}{i:>5}| {ln}")
    return "\n".join(out)
