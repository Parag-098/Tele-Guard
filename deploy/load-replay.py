#!/usr/bin/env python3
"""Measure authenticated synthetic-event inference on a running local TeleGuard API."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.longitudinal import TelecomConfig, TelecomGenerator


def request_json(url, payload, token=None, timeout=10):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urlopen(request, timeout=timeout) as response:
        return response.status, json.load(response)


def metric_sample(api_url, token):
    request = Request(f"{api_url}/system/metrics", headers={"Authorization": f"Bearer {token}"})
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def parse_memory(text):
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(B|KB|MB|GB|KiB|MiB|GiB)\s*", text, re.I)
    if not match:
        raise ValueError("unrecognized Docker memory usage")
    number, unit = match.groups()
    scale = {"B": 1, "KB": 1_000, "MB": 1_000_000, "GB": 1_000_000_000,
             "KIB": 1024, "MIB": 1024**2, "GIB": 1024**3}
    return int(float(number) * scale[unit.upper()])


class ContainerSampler:
    def __init__(self, names):
        self.names = names
        self.stop = threading.Event()
        self.samples = {}
        self.thread = None

    def start(self):
        if self.names:
            self.thread = threading.Thread(target=self._sample, daemon=True)
            self.thread.start()

    def _sample(self):
        while not self.stop.is_set():
            try:
                completed = subprocess.run(
                    ["docker", "stats", "--no-stream", "--format", "{{json .}}", *self.names],
                    check=True, capture_output=True, text=True, timeout=10,
                )
                for line in completed.stdout.splitlines():
                    sample = json.loads(line)
                    name = sample["Name"]
                    self.samples.setdefault(name, []).append(
                        parse_memory(sample["MemUsage"].split(" / ", 1)[0])
                    )
            except (OSError, subprocess.SubprocessError, ValueError):
                pass
            self.stop.wait(5)

    def finish(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=12)
        return {name: {"samples": len(values), "peak_bytes": max(values)}
                for name, values in self.samples.items() if values}


def percentile(values, quantile):
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(int((len(ordered) - 1) * quantile), len(ordered) - 1)], 2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000/api")
    parser.add_argument("--steady-seconds", type=int, default=600)
    parser.add_argument("--steady-rps", type=float, default=10)
    parser.add_argument("--burst-seconds", type=int, default=60)
    parser.add_argument("--burst-multiplier", type=float, default=2)
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--docker-containers", default="",
                        help="Comma-separated local container names to sample with docker stats")
    parser.add_argument("--output", type=Path, help="Create a new JSON evidence file")
    args = parser.parse_args()
    if (args.steady_seconds < 1 or args.burst_seconds < 0 or args.steady_rps <= 0
            or args.burst_multiplier < 1 or args.workers < 1):
        parser.error("durations, rates and worker counts must be positive; burst multiplier must be at least 1")
    username, password = os.getenv("TG_LOAD_USERNAME"), os.getenv("TG_LOAD_PASSWORD")
    if not username or not password:
        parser.error("set TG_LOAD_USERNAME and TG_LOAD_PASSWORD in the process environment")

    api_url = args.api_url.rstrip("/")
    _, session = request_json(f"{api_url}/auth/login", {"username": username, "password": password},
                              timeout=args.timeout)
    token = session["access_token"]
    before = metric_sample(api_url, token)
    run_id = uuid4().hex[:16]
    start = datetime.now(timezone.utc) - timedelta(days=7)
    generator = TelecomGenerator(TelecomConfig(
        seed=int(run_id[:8], 16), namespace=f"load-{run_id}", population=2_000,
        start=start, interval_seconds=60, prevalence=0.02, role="live",
    ))
    results = []
    schedule_start = time.monotonic()
    sampler = ContainerSampler([name.strip() for name in args.docker_containers.split(",") if name.strip()])
    sampler.start()

    def submit(index, due, phase):
        row = generator.record(index).event
        payload = row.model_dump(mode="json", exclude_none=True, exclude={"contract_version"})
        sent = time.monotonic()
        try:
            status, result = request_json(f"{api_url}/events", payload, token, args.timeout)
            prediction = result.get("prediction")
            valid = (status in {200, 201} and result.get("event", {}).get("event_id") == row.event_id
                     and isinstance(prediction, dict)
                     and isinstance(prediction.get("risk_score"), (int, float)))
            return {"ok": valid, "status": status, "phase": phase,
                    "latency_ms": (time.monotonic() - sent) * 1000,
                    "schedule_lag_ms": max(0.0, (sent - due) * 1000),
                    "event_id": row.event_id, "error_class": None if valid else "invalid_response"}
        except HTTPError as exc:
            return {"ok": False, "status": exc.code, "phase": phase,
                    "latency_ms": (time.monotonic() - sent) * 1000,
                    "schedule_lag_ms": max(0.0, (sent - due) * 1000),
                    "event_id": row.event_id, "error_class": "http_error"}
        except (OSError, URLError, TimeoutError, ValueError) as exc:
            return {"ok": False, "status": None, "phase": phase,
                    "latency_ms": (time.monotonic() - sent) * 1000,
                    "schedule_lag_ms": max(0.0, (sent - due) * 1000),
                    "event_id": row.event_id, "error_class": type(exc).__name__}

    futures = []
    index = 0
    phase_start = schedule_start
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        phases = (("steady", args.steady_seconds, args.steady_rps),
                  ("burst", args.burst_seconds, args.steady_rps * args.burst_multiplier))
        for phase, duration, rate in phases:
            count = int(duration * rate)
            for step in range(count):
                due = phase_start + step / rate
                delay = due - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                futures.append(pool.submit(submit, index, due, phase))
                index += 1
            phase_start += duration
        for future in as_completed(futures):
            results.append(future.result())

    container_peaks = sampler.finish()
    after = metric_sample(api_url, token)
    wall_seconds = time.monotonic() - schedule_start
    latencies = [item["latency_ms"] for item in results]
    phase_results = {}
    for phase, duration, _rate in phases:
        items = [item for item in results if item["phase"] == phase]
        successful_in_phase = sum(item["ok"] for item in items)
        phase_results[phase] = {
            "scheduled": len(items), "successful": successful_in_phase,
            "errors": len(items) - successful_in_phase,
            "observed_throughput_rps": round(successful_in_phase / max(duration, 0.001), 3),
            "request_latency_ms": {
                "p50": percentile([item["latency_ms"] for item in items], 0.50),
                "p95": percentile([item["latency_ms"] for item in items], 0.95),
                "max": round(max((item["latency_ms"] for item in items), default=0), 2)
                if items else None,
            },
            "schedule_lag_ms_p95": percentile([item["schedule_lag_ms"] for item in items], 0.95),
        }
    successful = sum(item["ok"] for item in results)
    errors = len(results) - successful
    persisted_before = before.get("persisted", {})
    persisted_after = after.get("persisted", {})
    report = {
        "schema": "teleguard-load-replay-v2", "run_id": run_id,
        "synthetic_only": True, "api_url": api_url,
        "schedule": {"steady_seconds": args.steady_seconds, "steady_rps": args.steady_rps,
                     "burst_seconds": args.burst_seconds,
                     "burst_multiplier": args.burst_multiplier, "workers": args.workers},
        "environment": {"platform": platform.platform(), "python": platform.python_version(),
                        "logical_cpus": os.cpu_count(), "container_memory": container_peaks},
        "results": {"scheduled": len(results), "successful": successful, "errors": errors,
                    "error_rate": errors / max(len(results), 1),
                    "observed_throughput_rps": round(successful / max(wall_seconds, 0.001), 3),
                    "wall_seconds": round(wall_seconds, 3),
                    "request_latency_ms": {"p50": percentile(latencies, 0.50),
                                           "p95": percentile(latencies, 0.95),
                                           "max": round(max(latencies), 2) if latencies else None},
                    "schedule_lag_ms_p95": percentile([item["schedule_lag_ms"] for item in results], 0.95),
                    "persisted_event_delta": persisted_after.get("events", 0) - persisted_before.get("events", 0),
                    "persisted_prediction_delta": persisted_after.get("predictions", 0) - persisted_before.get("predictions", 0),
                    "jobs_queued_after": persisted_after.get("jobs_queued"),
                    "jobs_running_after": persisted_after.get("jobs_running")},
        "per_status": {str(status): sum(item["status"] == status for item in results)
                        for status in sorted({item["status"] for item in results}, key=lambda x: str(x))},
        "phases": phase_results,
        "failure_samples": [
            {"event_id": item["event_id"], "status": item["status"],
             "error_class": item["error_class"]}
            for item in results if not item["ok"]
        ][:20],
        "error_classes": {name: sum(item["error_class"] == name for item in results)
                          for name in sorted({item["error_class"] for item in results if item["error_class"]})},
        "generator_namespace": f"load-{run_id}",
        "first_event_id": generator.record(0).event.event_id,
        "started_at_utc": datetime.fromtimestamp(time.time() - wall_seconds, timezone.utc).isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        with args.output.open("x", encoding="utf-8") as output:
            output.write(rendered + "\n")
    print(rendered)
    return 0 if (errors == 0 and report["results"]["persisted_event_delta"] >= successful
                 and report["results"]["persisted_prediction_delta"] >= successful) else 1


if __name__ == "__main__":
    raise SystemExit(main())
