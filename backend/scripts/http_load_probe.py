from __future__ import annotations

import argparse
import asyncio
import ipaddress
import os
import statistics
import sys
from dataclasses import dataclass
from time import perf_counter
from urllib.parse import urlsplit
from uuid import uuid4

import httpx


@dataclass(frozen=True, slots=True)
class OperationResult:
    elapsed_seconds: float
    error: str | None = None


def _is_loopback(base_url: str) -> bool:
    parsed = urlsplit(base_url)
    host = (parsed.hostname or "").strip().lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


async def _read_operation(client: httpx.AsyncClient) -> None:
    response = await client.get("/me")
    if response.status_code != 200:
        raise RuntimeError(f"GET /me returned HTTP {response.status_code}")


async def _project_write_operation(client: httpx.AsyncClient) -> None:
    project_id: str | None = None
    try:
        response = await client.post(
            "/projects",
            json={
                "name": f"load-probe-{uuid4().hex[:16]}",
                "description": "AuRoom bounded authenticated load probe",
                "context": {},
            },
        )
        if response.status_code != 201:
            raise RuntimeError(f"POST /projects returned HTTP {response.status_code}")
        payload = response.json()
        project_id = str(payload.get("id") or "")
        if not project_id:
            raise RuntimeError("POST /projects returned no project id")

        deleted = await client.delete(f"/projects/{project_id}")
        if deleted.status_code != 204:
            raise RuntimeError(f"DELETE /projects returned HTTP {deleted.status_code}")
        project_id = None
    finally:
        if project_id:
            try:
                await client.delete(f"/projects/{project_id}")
            except httpx.HTTPError:
                pass


async def _run_one(
    client: httpx.AsyncClient,
    *,
    mode: str,
    semaphore: asyncio.Semaphore,
) -> OperationResult:
    async with semaphore:
        started = perf_counter()
        try:
            if mode == "read":
                await _read_operation(client)
            else:
                await _project_write_operation(client)
            return OperationResult(perf_counter() - started)
        except Exception as exc:
            return OperationResult(
                perf_counter() - started,
                error=type(exc).__name__,
            )


async def run(args: argparse.Namespace) -> int:
    token = (os.getenv("AUROOM_LOAD_TOKEN") or "").strip()
    if not token:
        print("AUROOM_LOAD_TOKEN is required", file=sys.stderr)
        return 2

    base_url = args.base_url.rstrip("/")
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        print("base-url must be an absolute http(s) URL", file=sys.stderr)
        return 2
    if not parsed.path.rstrip("/").endswith("/api/v1"):
        print("base-url must point at the API v1 root, for example http://127.0.0.1:18001/api/v1", file=sys.stderr)
        return 2

    remote = not _is_loopback(base_url)
    if remote and parsed.scheme != "https":
        print("Refusing a remote load target without HTTPS", file=sys.stderr)
        return 2
    if remote and not args.allow_remote:
        print("Refusing a remote load target without --allow-remote", file=sys.stderr)
        return 2
    if remote and args.mode == "project-write" and not args.allow_remote_writes:
        print("Refusing remote writes without --allow-remote-writes", file=sys.stderr)
        return 2

    if args.requests < 1 or args.concurrency < 1:
        print("requests and concurrency must be positive", file=sys.stderr)
        return 2
    if args.concurrency > args.requests:
        args.concurrency = args.requests
    if not 0 <= args.max_error_rate <= 1:
        print("max-error-rate must be between 0 and 1", file=sys.stderr)
        return 2
    if args.max_p95_seconds is not None and args.max_p95_seconds <= 0:
        print("max-p95-seconds must be positive", file=sys.stderr)
        return 2

    timeout = httpx.Timeout(args.request_timeout_seconds)
    limits = httpx.Limits(
        max_connections=max(args.concurrency, 4),
        max_keepalive_connections=max(args.concurrency, 4),
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "AuRoomLoadProbe/1",
    }

    started = perf_counter()
    semaphore = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient(
        base_url=base_url,
        headers=headers,
        timeout=timeout,
        limits=limits,
    ) as client:
        results = await asyncio.gather(
            *[
                _run_one(client, mode=args.mode, semaphore=semaphore)
                for _ in range(args.requests)
            ]
        )
    elapsed = perf_counter() - started

    latencies = [item.elapsed_seconds for item in results]
    errors = [item for item in results if item.error]
    error_rate = len(errors) / len(results)
    p50 = _percentile(latencies, 0.50)
    p95 = _percentile(latencies, 0.95)
    p99 = _percentile(latencies, 0.99)
    throughput = len(results) / elapsed if elapsed > 0 else 0.0
    mean = statistics.fmean(latencies) if latencies else 0.0

    error_types: dict[str, int] = {}
    for item in errors:
        assert item.error is not None
        error_types[item.error] = error_types.get(item.error, 0) + 1

    print(
        "load_probe "
        f"mode={args.mode} operations={len(results)} concurrency={args.concurrency} "
        f"errors={len(errors)} error_rate={error_rate:.4f} elapsed_seconds={elapsed:.3f} "
        f"ops_per_second={throughput:.2f} mean_seconds={mean:.4f} "
        f"p50_seconds={p50:.4f} p95_seconds={p95:.4f} p99_seconds={p99:.4f}"
    )
    if error_types:
        print(
            "load_probe_error_types "
            + " ".join(f"{name}={count}" for name, count in sorted(error_types.items()))
        )

    if error_rate > args.max_error_rate:
        print(
            f"Load probe error rate {error_rate:.4f} exceeds {args.max_error_rate:.4f}",
            file=sys.stderr,
        )
        return 1
    if args.max_p95_seconds is not None and p95 > args.max_p95_seconds:
        print(
            f"Load probe p95 {p95:.4f}s exceeds {args.max_p95_seconds:.4f}s",
            file=sys.stderr,
        )
        return 1
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bounded authenticated AuRoom HTTP load probe")
    parser.add_argument("--base-url", required=True, help="API v1 root URL")
    parser.add_argument("--mode", choices=("read", "project-write"), default="read")
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--request-timeout-seconds", type=float, default=5.0)
    parser.add_argument("--max-error-rate", type=float, default=0.0)
    parser.add_argument("--max-p95-seconds", type=float)
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--allow-remote-writes", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
