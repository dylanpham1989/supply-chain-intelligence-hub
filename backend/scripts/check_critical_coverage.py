"""Fail when a security critical module drops below its own coverage floor.

The project-wide gate is 70 percent, which a suite can meet while leaving the
parts that enforce tenant isolation untested. These modules decide who sees
whose data, so they carry a separate and much higher floor.

Run after `pytest --cov --cov-report=json`.
"""

import json
import sys
from pathlib import Path

REPORT = Path("coverage.json")
FLOOR = 90.0

CRITICAL = (
    "app/core/security.py",
    "app/core/deps.py",
    "app/core/permissions.py",
    "app/core/cache.py",
    "app/db/rls.py",
    "ai/vectorstore/pgvector_store.py",
)


def main() -> int:
    if not REPORT.exists():
        print(f"{REPORT} not found, run pytest with --cov-report=json first")
        return 1

    files = json.loads(REPORT.read_text())["files"]
    failures: list[str] = []

    for module in CRITICAL:
        entry = files.get(module)
        if entry is None:
            failures.append(f"{module}: not in the coverage report")
            continue
        percent = entry["summary"]["percent_covered"]
        status = "ok" if percent >= FLOOR else "below floor"
        print(f"{module:40} {percent:6.1f}%  {status}")
        if percent < FLOOR:
            failures.append(f"{module}: {percent:.1f}% is below {FLOOR}%")

    if failures:
        print("\nsecurity critical coverage failed:")
        for failure in failures:
            print(f"  {failure}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
