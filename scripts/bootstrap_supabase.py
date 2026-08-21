#!/usr/bin/env python3
"""Apply the Supabase pgvector schema (tables, hnsw index, similarity RPC).

Usage:  python scripts/bootstrap_supabase.py
Reads SUPABASE_DB_URL (Transaction Pooler URI, port 6543) from backend/.env.
Idempotent - safe to re-run.
"""
import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

import config  # noqa: E402
from supabase_store import BOOTSTRAP_SQL  # noqa: E402

EXPECTED_TABLES = {"review_runs", "review_findings", "security_policies"}


async def main() -> int:
    if not config.SUPABASE_DB_URL:
        print("SUPABASE_DB_URL is not set in backend/.env.\n"
              "Supabase Dashboard -> Connect -> Transaction Pooler (port 6543).\n"
              "URL-encode special characters in the password ('@' -> '%40').\n\n"
              "No pooler URI? Start the backend and copy the SQL from "
              "GET /api/system/supabase-sql into the Supabase SQL Editor instead.")
        return 1

    try:
        import asyncpg
    except ImportError:
        print("asyncpg is missing. Run: pip install asyncpg")
        return 1

    try:
        conn = await asyncpg.connect(config.SUPABASE_DB_URL, statement_cache_size=0, timeout=30)
    except Exception as exc:
        print(f"connection failed: {exc}")
        print("Check the host is *.pooler.supabase.com on port 6543 and the password is URL-encoded.")
        return 1

    try:
        print("connected:", (await conn.fetchval("select version()"))[:60], "...")
        await conn.execute(BOOTSTRAP_SQL)
        print("applied bootstrap SQL")

        rows = await conn.fetch(
            "select table_name from information_schema.tables where table_schema='public'"
        )
        tables = sorted(r["table_name"] for r in rows)
        print("tables:", ", ".join(tables) or "(none)")

        missing = EXPECTED_TABLES - set(tables)
        if missing:
            print("MISSING:", ", ".join(sorted(missing)))
            return 1

        has_rpc = await conn.fetchval(
            "select count(*) from pg_proc where proname='match_security_policies'"
        )
        has_vec = await conn.fetchval("select count(*) from pg_extension where extname='vector'")
        print(f"match_security_policies(): {'present' if has_rpc else 'MISSING'}")
        print(f"vector extension: {'present' if has_vec else 'MISSING'}")

        policies = await conn.fetchval("select count(*) from security_policies")
        print(f"security_policies rows: {policies} "
              f"(the backend seeds 15 OWASP/CWE chunks on first boot)")
        return 0 if (has_rpc and has_vec) else 1
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
