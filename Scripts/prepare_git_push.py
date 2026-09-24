"""Remove vendored MCP and untrack generated paths before git push.

Run from repo root:
  venv\\Scripts\\python.exe Scripts\\prepare_git_push.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> int:
    print("+", " ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT)


def main() -> int:
    mcp = ROOT / "tigergraph-mcp"
    if mcp.is_dir():
        print(f"Removing {mcp} ...")
        shutil.rmtree(mcp, ignore_errors=True)

    for rel in (
        "tigergraph-mcp",
        "agent/.env",
        "venv",
        ".venv",
        "dashboard/node_modules",
        "dashboard/dist",
        "artifacts",
        "DATA/transactions.csv",
        "DATA/identity.csv",
    ):
        run(["git", "rm", "-r", "--cached", "--ignore-unmatch", rel])

    print("\nReady to stage: git add -A && git status")
    return 0


if __name__ == "__main__":
    sys.exit(main())
