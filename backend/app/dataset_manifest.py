"""Immutable, versioned synthetic snapshots with separate outcome data."""

import argparse
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
from hashlib import file_digest, sha256
from itertools import zip_longest
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from app.longitudinal import GENERATOR_VERSION, GeneratedRecord, SyntheticOutcome, TelecomConfig, TelecomGenerator
from app.schemas import EventIn

SCHEMA_VERSION = "teleguard-manifest-v1"
PART_SIZE = 10_000
DATASET_ROLES = ("development", "independent", "drift")
EXPECTED_VOLUMES = {"development": 300_000, "independent": 50_000, "drift": 50_000}
START_MONTHS = {"development": 1, "independent": 5, "drift": 6}


def canonical_json(value) -> bytes:
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("ascii")


def file_sha256(path: Path) -> str:
    with path.open("rb") as file:
        return file_digest(file, "sha256").hexdigest()


def partitions(role: str, count: int) -> dict[str, tuple[int, int]]:
    if role == "development":
        a, b, c = count * 70 // 100, count * 775 // 1000, count * 85 // 100
        return {"training": (0, a), "calibration": (a, b), "selection": (b, c), "test": (c, count)}
    if role == "drift":
        return {
            "reference": (0, count // 4),
            "shift": (count // 4, count // 2),
            "adaptation": (count // 2, count * 3 // 4),
            "recovery": (count * 3 // 4, count),
        }
    return {"independent": (0, count)}


@contextmanager
def compressed_part(path: Path):
    with path.open("xb") as stream, gzip.GzipFile(filename="", fileobj=stream, mode="wb", mtime=0) as part:
        yield part


def _outcome_payload(outcome: SyntheticOutcome) -> dict:
    payload = asdict(outcome)
    payload["available_at"] = outcome.available_at.isoformat()
    return payload


def _config_payload(config: TelecomConfig) -> dict:
    payload = asdict(config)
    payload["start"] = config.start.astimezone(timezone.utc).isoformat()
    return payload


def build_snapshot(
    root: Path, config: TelecomConfig, count: int, source_revision: str, part_size: int = PART_SIZE
) -> Path:
    """Write, verify, and atomically publish a deterministic snapshot directory."""
    if config.role not in DATASET_ROLES:
        raise ValueError("live runs are not offline snapshots")
    if not 40 <= count <= 1_000_000 or not 1 <= part_size <= 50_000:
        raise ValueError("invalid snapshot size or part size")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    configuration = {
        "generator_version": GENERATOR_VERSION, "count": count, "config": _config_payload(config),
        "part_size": part_size, "source_revision": source_revision,
    }
    version = f"{GENERATOR_VERSION}-{config.role}-{sha256(canonical_json(configuration)).hexdigest()[:20]}"
    target = root / version
    if (target / "manifest.json").exists():
        load_manifest(target / "manifest.json", verify_parts=True)
        return target / "manifest.json"

    generator = TelecomGenerator(config)
    split = partitions(config.role, count)
    split_summary = {}
    parts = []
    event_types, all_scenarios = Counter(), Counter()
    unique_events, subscribers, episodes = set(), set(), set()
    event_digest, outcome_digest = sha256(), sha256()
    first, last, final_label = None, None, None
    positives = 0
    with TemporaryDirectory(prefix=f".{version}-", dir=root) as staging:
        snapshot = Path(staging) / "snapshot"
        snapshot.mkdir()
        for split_name, (first_index, end_index) in split.items():
            label_count = 0
            split_digest = sha256()
            split_start, split_end, maximum_label_time = None, None, None
            phase = split_name if config.role == "drift" else "reference"
            for start_index in range(first_index, end_index, part_size):
                stop_index = min(start_index + part_size, end_index)
                part_id = f"{split_name}-{start_index:07d}"
                event_file = snapshot / f"{part_id}.events.jsonl.gz"
                label_file = snapshot / f"{part_id}.labels.jsonl.gz"
                with compressed_part(event_file) as event_part, compressed_part(label_file) as label_part:
                    for index in range(start_index, stop_index):
                        generated = generator.record(index, phase)
                        event, label = generated.event, generated.outcome
                        if event.event_id in unique_events or (last and event.event_time <= last):
                            raise ValueError("duplicate or disordered generated event")
                        first = first or event.event_time
                        last = event.event_time
                        final_label = max(final_label or label.available_at, label.available_at)
                        split_start = split_start or event.event_time
                        split_end = event.event_time
                        maximum_label_time = max(maximum_label_time or label.available_at, label.available_at)
                        label_count += label.label
                        unique_events.add(event.event_id)
                        subscribers.add(event.subscriber_id)
                        if label.episode_id:
                            episodes.add(label.episode_id)
                        event_types[event.event_type] += 1
                        all_scenarios[label.scenario] += 1
                        event_line = canonical_json(event.model_dump(mode="json", exclude_none=True))
                        outcome_line = canonical_json(_outcome_payload(label))
                        event_part.write(event_line)
                        label_part.write(outcome_line)
                        event_digest.update(event_line)
                        outcome_digest.update(outcome_line)
                        split_digest.update(canonical_json({"event_id": event.event_id, "position": index}))
                parts.append({
                    "split": split_name, "rows": stop_index - start_index,
                    "events": event_file.name, "event_sha256": file_sha256(event_file),
                    "outcomes": label_file.name, "outcome_sha256": file_sha256(label_file),
                })
            positives += label_count
            split_summary[split_name] = {
                "start_index": first_index, "end_index_exclusive": end_index,
                "rows": end_index - first_index, "positives": label_count,
                "assignment_sha256": split_digest.hexdigest(),
                "event_start": split_start.isoformat(), "event_end": split_end.isoformat(),
                "all_outcomes_available_at": maximum_label_time.isoformat(),
            }

        manifest = {
            **configuration, "version": version, "schema_version": SCHEMA_VERSION,
            "event_contract": "event-v1", "normalization_version": "event-v1-utc-json",
            "known_quality": "synthetic optional missingness and overlapping lookalikes",
            "provenance": "TeleGuard artificial telecommunications simulation",
            "source_rights": "first-party synthetic generation; no external subscriber data",
            "unique_events": len(unique_events), "subscribers": len(subscribers),
            "fraud_episodes": len(episodes), "positive_events": positives,
            "negative_events": count - positives, "realized_prevalence": positives / count,
            "event_types": dict(event_types), "scenarios": dict(all_scenarios),
            "event_start": first.isoformat(), "event_end": last.isoformat(),
            "ingestion_cutoff": last.isoformat(), "all_outcomes_available_at": final_label.isoformat(),
            "events_sha256": event_digest.hexdigest(), "outcomes_sha256": outcome_digest.hexdigest(),
            "splits": split_summary, "parts": parts,
        }
        manifest["manifest_sha256"] = sha256(canonical_json(manifest)).hexdigest()
        staging_manifest = snapshot / "manifest.json"
        staging_manifest.write_bytes(canonical_json(manifest))
        load_manifest(staging_manifest, verify_parts=True)
        # Renaming a completed directory on the same filesystem avoids partial publication.
        try:
            snapshot.rename(target)
        except OSError:
            if not (target / "manifest.json").is_file():
                raise
            winner = load_manifest(target / "manifest.json", verify_parts=True)
            if winner["manifest_sha256"] != manifest["manifest_sha256"]:
                raise RuntimeError("existing version has different content") from None
    return target / "manifest.json"


def _part_path(manifest_path: Path, part_name: str) -> Path:
    if Path(part_name).name != part_name or not part_name.endswith(".jsonl.gz"):
        raise ValueError("invalid snapshot part name")
    parent = manifest_path.parent.resolve()
    part = (parent / part_name).resolve()
    if part.parent != parent:
        raise ValueError("snapshot part points outside its manifest directory")
    return part


def load_manifest(path: Path, *, verify_parts: bool = False) -> dict:
    path = Path(path)
    manifest = json.loads(path.read_bytes())
    actual_digest = manifest.pop("manifest_sha256")
    if (
        manifest["schema_version"] != SCHEMA_VERSION
        or sha256(canonical_json(manifest)).hexdigest() != actual_digest
    ):
        raise ValueError("invalid dataset manifest digest or schema")
    manifest["manifest_sha256"] = actual_digest
    if verify_parts:
        for part in manifest["parts"]:
            for key, digest in (("events", "event_sha256"), ("outcomes", "outcome_sha256")):
                if file_sha256(_part_path(path, part[key])) != part[digest]:
                    raise ValueError(f"dataset content checksum mismatch for {part[key]}")
    return manifest


def iter_records(path: Path, manifest: dict):
    """Read aligned validated payload and label streams in canonical event order."""
    last = None
    total = 0
    seen = set()
    events_digest, outcomes_digest = sha256(), sha256()
    declared_partitions = partitions(manifest["config"]["role"], manifest["count"])
    assignment_digests = {name: sha256() for name in declared_partitions}
    positive_by_split = Counter()
    for part in manifest["parts"]:
        split = part["split"]
        minimum, maximum = declared_partitions[split]
        if not minimum <= total < total + part["rows"] <= maximum:
            raise ValueError("snapshot part is outside its declared chronological split")
        rows = 0
        with (
            gzip.open(_part_path(path, part["events"]), "rb") as events,
            gzip.open(_part_path(path, part["outcomes"]), "rb") as outcomes,
        ):
            for event_line, outcome_line in zip_longest(events, outcomes):
                if event_line is None or outcome_line is None:
                    raise ValueError("snapshot events and outcomes have different row counts")
                payload = json.loads(event_line)
                if {"fraud_label", "scenario_label"}.intersection(payload):
                    raise ValueError("outcome metadata leaked into event payload")
                outcome = json.loads(outcome_line)
                event = EventIn.model_validate(payload)
                if last and event.event_time <= last:
                    raise ValueError("snapshot event order is not strictly chronological")
                last = event.event_time
                outcome["available_at"] = datetime.fromisoformat(outcome["available_at"])
                label = SyntheticOutcome(**outcome)
                if (
                    label.event_id != event.event_id
                    or label.label not in {0, 1}
                    or bool(label.episode_id) != bool(label.label)
                    or label.available_at <= event.event_time
                    or (manifest["config"]["role"] == "drift" and label.phase != part["split"])
                ):
                    raise ValueError("invalid or misaligned synthetic outcome")
                if event.event_id in seen:
                    raise ValueError("duplicate ID in snapshot")
                seen.add(event.event_id)
                events_digest.update(event_line)
                outcomes_digest.update(outcome_line)
                assignment_digests[split].update(canonical_json({"event_id": event.event_id, "position": total}))
                positive_by_split[split] += label.label
                rows += 1
                total += 1
                yield part["split"], GeneratedRecord(event, label)
        if rows != part["rows"]:
            raise ValueError("manifest part count differs from stored rows")
    if total != manifest["unique_events"] or total != manifest["count"]:
        raise ValueError("manifest count differs from stored unique events")
    for name, (start, end) in declared_partitions.items():
        summary = manifest["splits"][name]
        if (
            (summary["start_index"], summary["end_index_exclusive"]) != (start, end)
            or summary["rows"] != end - start
            or assignment_digests[name].hexdigest() != summary["assignment_sha256"]
            or positive_by_split[name] != summary["positives"]
        ):
            raise ValueError(f"dataset split evidence mismatch in {name}")
    if (
        events_digest.hexdigest() != manifest["events_sha256"]
        or outcomes_digest.hexdigest() != manifest["outcomes_sha256"]
    ):
        raise ValueError("manifest stream digest differs from stored events or outcomes")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261128)
    parser.add_argument("--source-revision", default=os.environ.get("TG_SOURCE_REVISION", "workspace"))
    parser.add_argument("--small", action="store_true", help="create reduced smoke datasets")
    parser.add_argument("--prevalence-sweep", action="store_true", help="include four independent cohorts")
    args = parser.parse_args()
    outputs = {}
    for role, default_count in EXPECTED_VOLUMES.items():
        config = TelecomConfig(
            seed=args.seed, namespace=f"{role}-{args.seed}", role=role,
            start=datetime(2025, START_MONTHS[role], 1, tzinfo=timezone.utc),
        )
        smoke_count = 20_000 if role == "development" else 5_000
        outputs[role] = str(build_snapshot(
            args.root, config, smoke_count if args.small else default_count, args.source_revision
        ))
    if args.prevalence_sweep:
        for level in (0.005, 0.01, 0.02, 0.05):
            basis_points = int(level * 10_000)
            config = TelecomConfig(
                seed=args.seed, namespace=f"prevalence-{basis_points}-{args.seed}", role="independent",
                start=datetime(2025, 7, 1, tzinfo=timezone.utc), prevalence=level,
            )
            outputs[f"prevalence_{basis_points}_bps"] = str(
                build_snapshot(args.root, config, 5_000 if args.small else 20_000, args.source_revision)
            )
    print(json.dumps(outputs, indent=2))


if __name__ == "__main__":
    main()
