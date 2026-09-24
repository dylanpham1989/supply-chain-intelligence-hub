"""Latency for the endpoints a dashboard actually waits on.

Sequential, one client, warm cache where the endpoint has one. This measures the
server, not concurrency: numbers from a laptop with everything on one machine
say what the code costs, not what the system can take.

    uv run python -m scripts.bench --base-url http://localhost:8000
"""

import argparse
import asyncio
import statistics
import time
from typing import Any

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"
WARMUP = 5
RUNS = 100

LOGIN = {
    "tenant_slug": "acme-logistics",
    "email": "admin@acme.test",
    "password": "Demo1234!",
}

ENDPOINTS: list[tuple[str, str]] = [
    ("shipments, page 1", "/api/v1/shipments?page=1&size=20"),
    ("shipments, filtered", "/api/v1/shipments?status=delayed&page=1&size=20"),
    ("shipments, page 5", "/api/v1/shipments?page=5&size=20"),
    ("analytics summary", "/api/v1/analytics/summary"),
    ("analytics timeseries", "/api/v1/analytics/shipments-timeseries?days=365"),
    ("suppliers", "/api/v1/suppliers?page=1&size=20"),
    ("documents", "/api/v1/documents?page=1&size=20"),
    ("health, ready", "/health/ready"),
]


async def measure(client: httpx.AsyncClient, path: str, runs: int) -> tuple[list[float], str]:
    samples: list[float] = []
    cache = ""
    for _ in range(runs):
        started = time.perf_counter()
        response = await client.get(path)
        response.raise_for_status()
        samples.append((time.perf_counter() - started) * 1000)
        cache = response.headers.get("x-cache", cache)
    return samples, cache


def summarise(name: str, samples: list[float], cache: str) -> dict[str, Any]:
    ordered = sorted(samples)
    # method="inclusive" keeps the result inside the observed range. The default
    # extrapolates, which produced a p99 above the maximum on the first run.
    return {
        "name": name,
        "p50": statistics.median(ordered),
        "p95": statistics.quantiles(ordered, n=20, method="inclusive")[18],
        "p99": statistics.quantiles(ordered, n=100, method="inclusive")[98],
        "max": ordered[-1],
        "cache": cache or "n/a",
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--runs", type=int, default=RUNS)
    args = parser.parse_args()

    async with httpx.AsyncClient(base_url=args.base_url, timeout=30) as client:
        login = await client.post("/api/v1/auth/login", json=LOGIN)
        login.raise_for_status()
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

        rows = []
        for name, path in ENDPOINTS:
            await measure(client, path, WARMUP)
            samples, cache = await measure(client, path, args.runs)
            rows.append(summarise(name, samples, cache))

    width = max(len(row["name"]) for row in rows)
    print(f"{args.runs} requests each, sequential, against {args.base_url}\n")
    print(f"{'endpoint':<{width}}  {'p50':>8}  {'p95':>8}  {'p99':>8}  {'max':>8}  cache")
    for row in rows:
        print(
            f"{row['name']:<{width}}  {row['p50']:>7.1f}ms  {row['p95']:>7.1f}ms  "
            f"{row['p99']:>7.1f}ms  {row['max']:>7.1f}ms  {row['cache']}"
        )


if __name__ == "__main__":
    asyncio.run(main())
