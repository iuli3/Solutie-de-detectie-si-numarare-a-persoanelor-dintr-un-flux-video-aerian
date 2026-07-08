#!/usr/bin/env python3
import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request_json(method, url, payload=None, token=None, timeout=10):
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    started = time.perf_counter()
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as response:
            response.read()
            status = response.status
    except HTTPError as exc:
        exc.read()
        status = exc.code
    except URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc}") from exc
    elapsed_ms = (time.perf_counter() - started) * 1000
    return status, elapsed_ms


def login(base_url, username, password):
    payload = json.dumps({"username": username, "password": password}).encode("utf-8")
    req = Request(
        f"{base_url}/auth/login",
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=10) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data["access_token"]


def percentile(values, pct):
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((pct / 100) * (len(ordered) - 1)))
    return ordered[index]


def main():
    parser = argparse.ArgumentParser(description="Performance smoke test for the Flask API")
    parser.add_argument("--base-url", required=True, help="Example: http://127.0.0.1:5000")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--max-p95-ms", type=float, default=500)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    token = login(base_url, args.username, args.password)

    def hit_dashboard():
        return request_json("GET", f"{base_url}/api/dashboard-stats", token=token)

    statuses = []
    timings = []
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(hit_dashboard) for _ in range(args.requests)]
        for future in as_completed(futures):
            status, elapsed_ms = future.result()
            statuses.append(status)
            timings.append(elapsed_ms)

    total_seconds = time.perf_counter() - started
    failures = [status for status in statuses if status >= 400]
    p95 = percentile(timings, 95)

    print(f"requests={args.requests} concurrency={args.concurrency}")
    print(f"success={len(statuses) - len(failures)} failures={len(failures)} throughput={args.requests / total_seconds:.2f} req/s")
    print(f"avg_ms={statistics.mean(timings):.1f} median_ms={statistics.median(timings):.1f} p95_ms={p95:.1f} max_ms={max(timings):.1f}")

    if failures:
        raise SystemExit(f"Performance smoke failed: HTTP failures {failures[:10]}")
    if p95 > args.max_p95_ms:
        raise SystemExit(f"Performance smoke failed: p95 {p95:.1f}ms > {args.max_p95_ms:.1f}ms")


if __name__ == "__main__":
    main()
