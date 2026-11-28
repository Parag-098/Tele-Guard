"""Shared classifier decisions and deterministic release routing."""

from hashlib import sha256

from sqlalchemy import text

from app.config import settings


def classifier_threshold(model=None):
    return (model or {}).get("classification_threshold", settings.classification_threshold)


def classifier_decision(probability, model=None):
    return probability >= classifier_threshold(model)


def assigned_canary(subscriber_id: str, serving: dict) -> bool:
    if serving.get("mode") != "canary":
        return False
    namespace = serving.get("experiment_id") or serving.get("challenger_version") or "teleguard"
    key = f"{namespace}\0{subscriber_id}".encode("utf-8")
    bucket = int.from_bytes(sha256(key).digest()[:8], "big") % 10_000
    return bucket < int(serving["canary_percent"]) * 100


def lock_model_release(db) -> None:
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(1712527019)"))
