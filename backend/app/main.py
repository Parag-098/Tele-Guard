from contextlib import asynccontextmanager
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import csv
import io
import os
import time
import urllib.request
from uuid import uuid4
import re
import numpy as np
import joblib
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import and_, case, func, select, or_
from sqlalchemy.orm import Session
from app.config import settings
from app.db import Base, engine, get_db, SessionLocal
from app.models import (
    User,
    Event,
    Prediction,
    Incident,
    AuditLog,
    Note,
    ModelRun,
    ResponseAction,
    AuthSession,
    DemoDataset,
    MLOpsRecord,
    ModelObservation,
    DatasetVersion,
    MLOpsJob,
    ServiceHeartbeat,
)
from app.schemas import EventIn, LoginIn, NoteIn, IncidentUpdate, ActionIn, SeedDatasetIn, JobControlIn
from app.security import allow, current_user, hash_password, verify_password, make_token, oauth
from app.ml import (
    load_model,
    score,
    train_model,
    track_training_run,
    FEATURE_VERSION,
    FEATURES,
    features,
    explain_prediction,
    model_input,
    FeatureState,
)
from app.synthetic import generate_events
from app.batch_scoring import BatchScoringState
from app.dataset_jobs import (
    MAX_INITIAL_ROWS,
    MIN_INITIAL_ROWS,
    dataset_version_for,
    queue_job,
)

_API_STARTED = time.monotonic()
_HTTP_STATS = {"requests": 0, "errors": 0, "latency_ms_total": 0.0}


def load_model_run(model_run: ModelRun) -> dict:
    """Load a trusted recorded model artifact, downloading it from MLflow when needed."""
    artifact_path = model_run.artifact_path
    if not artifact_path or not artifact_path.endswith(".joblib"):
        raise RuntimeError("Recorded model artifact path is invalid")
    try:
        return joblib.load(artifact_path)
    except FileNotFoundError:
        if not model_run.mlflow_run_id:
            raise
    from mlflow import MlflowClient

    local_path = MlflowClient().download_artifacts(
        run_id=model_run.mlflow_run_id,
        path=artifact_path.replace("\\", "/").rsplit("/", 1)[-1],
    )
    return joblib.load(local_path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    app.state.model = load_model()
    with SessionLocal() as db:
        active = (
            db.query(MLOpsRecord)
            .filter_by(kind="active_model")
            .order_by(MLOpsRecord.id.desc())
            .first()
        )
        if active:
            selected = db.query(ModelRun).filter_by(version=active.version).first()
            if not selected:
                raise RuntimeError(
                    f"Active model {active.version} has no persisted model-run record"
                )
            try:
                app.state.model = load_model_run(selected)
            except (OSError, ValueError, KeyError) as exc:
                raise RuntimeError(
                    f"Active model artifact {active.version} cannot be loaded"
                ) from exc
            if app.state.model.get("version") != active.version:
                raise RuntimeError(f"Active model artifact version does not match {active.version}")
        else:
            db.add(
                MLOpsRecord(
                    kind="active_model",
                    version=app.state.model["version"],
                    payload={"reason": "initial baseline selection"},
                    created_by="system",
                )
            )
            db.add(
                MLOpsRecord(
                    kind="approved_model",
                    version=app.state.model["version"],
                    payload={"reason": "initial baseline model"},
                    created_by="system",
                )
            )
        if not db.query(ModelRun).filter_by(version=app.state.model["version"]).first():
            db.add(
                ModelRun(
                    version=app.state.model["version"],
                    algorithm=app.state.model["algorithm"],
                    dataset_version="scenario-v1-seed-2026",
                    metrics=app.state.model.get("metrics", {}),
                    artifact_path=app.state.model["artifact_path"],
                )
            )
            db.commit()
    yield


app = FastAPI(
    title="TeleGuard AI",
    version="0.1.0",
    description="Synthetic telecom fraud simulation API",
    openapi_url="/openapi.json" if settings.enable_api_docs else None,
    docs_url="/docs" if settings.enable_api_docs else None,
    redoc_url="/redoc" if settings.enable_api_docs else None,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def collect_request_metrics(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
        if response.status_code >= 500:
            _HTTP_STATS["errors"] += 1
        return response
    except Exception:
        _HTTP_STATS["errors"] += 1
        raise
    finally:
        _HTTP_STATS["requests"] += 1
        _HTTP_STATS["latency_ms_total"] += (time.perf_counter() - started) * 1000


def log(db, actor, action, target, reason=None, details=None):
    db.add(
        AuditLog(actor=actor, action=action, target=target, reason=reason, details=details or {})
    )


def event_dict(e):
    return {
        "event_id": e.event_id,
        "event_type": e.event_type,
        "event_time": e.event_time.isoformat(),
        "subscriber_id": e.subscriber_id,
        "source_token": e.source_token,
        "destination_token": e.destination_token,
        "sim_id": e.sim_id,
        "device_id": e.device_id,
        "network_token": e.network_token,
        "location_token": e.location_token,
        "latitude": e.latitude,
        "longitude": e.longitude,
        "duration_seconds": e.duration_seconds,
        "call_direction": e.call_direction,
        "call_status": e.call_status,
        "is_international": e.is_international,
        "is_roaming": e.is_roaming,
        "message_count": e.message_count,
        "auth_outcome": e.auth_outcome,
        "scenario_label": e.scenario_label,
        "contract_version": "event-v1",
    }


def prediction_dict(p):
    return {
        "id": p.id,
        "event_id": p.event_id,
        "model_version": p.model_version,
        "feature_version": p.feature_version,
        "policy_version": p.policy_version,
        "probability": p.probability,
        "anomaly_score": p.anomaly_score,
        "graph_score": p.graph_score,
        "rule_score": p.rule_score,
        "risk_score": p.risk_score,
        "risk_band": p.risk_band,
        "evidence": p.evidence,
        "explanation": p.explanation,
        "ground_truth_label": p.ground_truth_label,
        "label_source": p.label_source,
        "label_received_at": p.label_received_at.isoformat() if p.label_received_at else None,
        "created_at": p.created_at.isoformat(),
    }


def score_event(db, event, user, model):
    active_version = _mlops_state(db)
    if model.get("version") != active_version:
        selected_run = db.query(ModelRun).filter_by(version=active_version).first()
        if not selected_run:
            raise RuntimeError(f"Active model {active_version} has no persisted model-run record")
        model = load_model_run(selected_run)
        if model.get("version") != active_version:
            raise RuntimeError("Selected champion artifact version does not match PostgreSQL active state")
        app.state.model = model
    prior = (
        db.query(Event)
        .filter(
            Event.subscriber_id == event.subscriber_id,
            Event.id != event.id,
            Event.event_time <= event.event_time,
        )
        .order_by(Event.event_time.desc())
        .limit(200)
        .all()
    )
    shared_entity_filters = []
    if event.device_id:
        shared_entity_filters.append(Event.device_id == event.device_id)
    if event.network_token:
        shared_entity_filters.append(Event.network_token == event.network_token)
    linked = (
        db.query(Event)
        .filter(
            Event.event_time <= event.event_time,
            Event.subscriber_id != event.subscriber_id,
            or_(*shared_entity_filters),
        )
        .limit(200)
        .all()
        if shared_entity_filters
        else []
    )
    context = [event_dict(x) for x in {x.id: x for x in prior + linked}.values()]
    event_row = event_dict(event)
    result = score(event_row, model, context)
    scenario_result = evaluate_location_scenario(db, event_row, context)
    context_weight = float(scenario_result["configuration"]["risk_weight"])
    result["risk_score"] = float(np.clip(result["risk_score"] + context_weight * scenario_result["risk_score"], 0, 1))
    result["risk_band"] = "Critical" if result["risk_score"] >= 0.8 else "High" if result["risk_score"] >= 0.6 else "Medium" if result["risk_score"] >= 0.35 else "Low"
    result["evidence"].append({"signal": "location_travel_scenario", "value": scenario_result["risk_score"], "detail": scenario_result["summary"], "findings": scenario_result["findings"]})
    observations = [(model.get("version", settings.model_version), "champion", result["probability"])]
    serve_config = current_serving_config(db)
    challenger_version = serve_config.get("challenger_version")
    if serve_config.get("mode") in {"shadow", "canary"} and challenger_version and challenger_version != model.get("version"):
        challenger_row = db.query(ModelRun).filter_by(version=challenger_version).first()
        if challenger_row:
            try:
                challenger = load_model_run(challenger_row)
                challenger_result = score(event_row, challenger, context)
                canary = serve_config.get("mode") == "canary" and (int(event.event_id.encode().hex()[:8], 16) % 100 < int(serve_config.get("canary_percent", 0)))
                observations.append((challenger_version, "canary" if canary else "shadow", challenger_result["probability"]))
                if canary:
                    result.update(challenger_result)
                    result["risk_score"] = float(np.clip(result["risk_score"] + context_weight * scenario_result["risk_score"], 0, 1))
                    result["risk_band"] = "Critical" if result["risk_score"] >= 0.8 else "High" if result["risk_score"] >= 0.6 else "Medium" if result["risk_score"] >= 0.35 else "Low"
                    result["evidence"].append({"signal": "location_travel_scenario", "value": scenario_result["risk_score"], "detail": scenario_result["summary"], "findings": scenario_result["findings"]})
                    model = challenger
            except Exception as exc:
                log(db, "system", "model.challenger_failed", challenger_version, reason=str(exc)[:250], details={"champion_retained": True, "event_id": event.event_id})
    p = Prediction(
        event_id=event.event_id,
        model_version=model.get("version", settings.model_version),
        feature_version=result.get("feature_version", FEATURE_VERSION),
        policy_version=settings.risk_policy_version,
        **{
            k: result[k]
            for k in (
                "probability",
                "anomaly_score",
                "graph_score",
                "rule_score",
                "risk_score",
                "risk_band",
                "evidence",
            )
        },
    )
    db.add(p)
    db.flush()
    for version, role, probability in observations:
        db.add(ModelObservation(prediction_id=p.id, model_version=version, serving_role=role, probability=probability, predicted_label=int(probability >= 0.5)))
    if p.risk_score >= settings.incident_risk_threshold:
        db.add(
            Incident(
                prediction_id=p.id,
                subscriber_id=event.subscriber_id,
                title=f"Elevated synthetic risk — {event.event_type}",
                severity=p.risk_band,
            )
        )
    log(db, user.username, "event.scored", event.event_id, details={"risk_band": p.risk_band})
    return p


def evaluate_location_scenario(db, row, context):
    config = current_scenario_config(db)
    findings = []
    prior = [x for x in context if x.get("subscriber_id") == row["subscriber_id"] and x.get("event_time") and x.get("event_time") <= row["event_time"]]
    prior.sort(key=lambda x: x["event_time"], reverse=True)
    if row.get("latitude") is not None and row.get("longitude") is not None:
        located = next((x for x in prior if x.get("latitude") is not None and x.get("longitude") is not None), None)
        if located:
            from math import asin, cos, radians, sin, sqrt
            lat1, lon1 = radians(float(located["latitude"])), radians(float(located["longitude"]))
            lat2, lon2 = radians(float(row["latitude"])), radians(float(row["longitude"]))
            dlat, dlon = lat2-lat1, lon2-lon1
            distance = 6371 * 2 * asin(sqrt(sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2))
            old_time = datetime.fromisoformat(located["event_time"].replace("Z", "+00:00"))
            new_time = datetime.fromisoformat(row["event_time"].replace("Z", "+00:00"))
            old_time = old_time.replace(tzinfo=timezone.utc) if old_time.tzinfo is None else old_time
            new_time = new_time.replace(tzinfo=timezone.utc) if new_time.tzinfo is None else new_time
            minutes = (new_time-old_time).total_seconds()/60
            if 0 < minutes <= float(config["impossible_travel_minutes"]) and distance / (minutes/60) > float(config["max_speed_kmh"]):
                findings.append({"code":"impossible_travel", "distance_km":round(distance,1), "elapsed_minutes":round(minutes,1), "detail":"Recorded coordinates imply travel beyond the configured speed limit."})
    elif not row.get("location_token"):
        findings.append({"code":"location_unavailable", "detail":"No location token or coordinates were supplied; geographic checks were skipped."})
    location = row.get("location_token")
    history = [x.get("location_token") for x in prior if x.get("location_token")]
    if location and len(history) >= int(config["unusual_location_min_history"]) and location not in history:
        findings.append({"code":"unusual_geography", "detail":"Location token is new for this subscriber's available event history; review context before treating as suspicious."})
    for name, rule in config.get("scenario_rules", {}).items():
        if not isinstance(rule, dict):
            continue
        if ((rule.get("event_type") and rule.get("event_type") == row.get("event_type")) or
                (rule.get("location_token") and rule.get("location_token") == row.get("location_token"))):
            findings.append({"code":"configured_scenario", "scenario":str(name)[:80], "detail":str(rule.get("description", "Configured event/location risk scenario"))[:240]})
    risk = min(1.0, 0.8 if any(f["code"] == "impossible_travel" for f in findings) else 0.35 if any(f["code"] in {"unusual_geography", "configured_scenario"} for f in findings) else 0.0)
    return {"risk_score":risk,"findings":findings,"configuration":config,"summary":"; ".join(f["detail"] for f in findings) if findings else ("Location history checked; no configured concern found." if row.get("location_token") or row.get("latitude") is not None else "Location/travel context unavailable; geographic checks skipped safely.")}


def current_serving_config(db):
    row = db.query(MLOpsRecord).filter_by(kind="serving_config").order_by(MLOpsRecord.id.desc()).first()
    return row.payload if row else {"mode":"champion", "challenger_version":None, "canary_percent":0}


def current_scenario_config(db):
    row = db.query(MLOpsRecord).filter_by(kind="scenario_config").order_by(MLOpsRecord.id.desc()).first()
    return {"max_speed_kmh": 900.0, "impossible_travel_minutes": 120, "risk_weight": 0.2, "unusual_location_min_history": 4, **(row.payload if row else {})}


def _stop_challenger_serving(db, actor, reason):
    config = current_serving_config(db)
    if config.get("mode") != "champion":
        payload = {"mode": "champion", "challenger_version": None, "canary_percent": 0}
        _record(db, "serving_config", f"serving-{uuid4().hex[:12]}", payload, actor)
        log(db, actor, "model.serving_stopped", config.get("challenger_version") or "challenger", reason=reason, details=payload)


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok", "database": "connected", "contract_version": "event-v1"}


@app.get("/api/system/health")
def system_health(db: Session = Depends(get_db), user: User = Depends(current_user)):
    database_ok = True
    try:
        db.execute(select(1))
    except Exception:
        database_ok = False
    worker = db.get(ServiceHeartbeat, "worker")
    worker_age = None
    worker_ok = False
    if worker:
        updated = worker.updated_at
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        worker_age = max(0.0, (datetime.now(timezone.utc) - updated).total_seconds())
        worker_ok = worker.status == "healthy" and worker_age <= 45
    mlflow_uri = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000").rstrip("/")
    try:
        with urllib.request.urlopen(f"{mlflow_uri}/health", timeout=0.7) as response:
            mlflow_ok = response.status == 200
    except Exception:
        mlflow_ok = False
    return {
        "status": "ok" if database_ok and worker_ok and mlflow_ok else "degraded",
        "api": {"status": "healthy", "uptime_seconds": round(time.monotonic() - _API_STARTED, 1)},
        "database": {"status": "healthy" if database_ok else "unavailable"},
        "worker": {"status": "healthy" if worker_ok else "unavailable", "last_seen_seconds": worker_age,
                   "current_job_id": worker.current_job_id if worker else None},
        "mlflow": {"status": "healthy" if mlflow_ok else "unavailable"},
    }


@app.get("/api/system/metrics")
def system_metrics(db: Session = Depends(get_db), user: User = Depends(current_user)):
    now_utc = datetime.now(timezone.utc)
    recent_events = db.query(Event).filter(Event.created_at >= now_utc - timedelta(hours=1)).count()
    requests = _HTTP_STATS["requests"]
    return {
        "persisted": {
            "events": db.query(Event).count(), "predictions": db.query(Prediction).count(),
            "incidents": db.query(Incident).count(), "datasets": db.query(DatasetVersion).count(),
            "jobs_running": db.query(MLOpsJob).filter(MLOpsJob.status == "running").count(),
            "jobs_queued": db.query(MLOpsJob).filter(MLOpsJob.status == "queued").count(),
        },
        "ingestion": {"events_last_hour": recent_events, "events_per_minute_last_hour": round(recent_events / 60, 2)},
        "api_process": {
            "requests_since_start": requests,
            "server_error_responses": _HTTP_STATS["errors"],
            "mean_request_ms": round(_HTTP_STATS["latency_ms_total"] / max(requests, 1), 2),
            "uptime_seconds": round(time.monotonic() - _API_STARTED, 1),
        },
        "measured_at": now_utc.isoformat(),
    }


@app.get("/api/data/observatory")
def data_observatory(db: Session = Depends(get_db), user: User = Depends(current_user)):
    event_count = db.query(Event).count()
    fields = ("duration_seconds", "device_id", "network_token", "location_token", "latitude", "longitude")
    null_counts = {
        field: db.query(Event).filter(getattr(Event, field).is_(None)).count()
        for field in fields
    }
    return {
        "events": event_count,
        "predictions": db.query(Prediction).count(),
        "incidents": db.query(Incident).count(),
        "missing_values": {field: {"count": count, "rate": count / max(event_count, 1)}
                           for field, count in null_counts.items()},
        "event_types": [{"event_type": event_type, "rows": count}
                        for event_type, count in db.query(Event.event_type, func.count(Event.id)).group_by(Event.event_type).order_by(Event.event_type).all()],
        "labels": [{"fraud_label": label, "rows": count}
                   for label, count in db.query(Event.fraud_label, func.count(Event.id)).group_by(Event.fraud_label).order_by(Event.fraud_label).all()],
        "datasets": [{"version": row.version, "kind": row.kind, "rows": row.row_count,
                      "target_rows": row.target_rows, "status": row.status, "seed": row.seed}
                     for row in db.query(DatasetVersion).order_by(DatasetVersion.created_at.desc()).all()],
    }


@app.post("/api/auth/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(username=data.username, active=True).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Invalid username or password")
    token_id = uuid4().hex
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.token_minutes)
    db.add(AuthSession(token_id=token_id, username=user.username, expires_at=expires_at))
    log(db, user.username, "auth.login", user.username)
    db.commit()
    return {
        "access_token": make_token(user, token_id),
        "token_type": "bearer",
        "user": {"username": user.username, "role": user.role},
    }


@app.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return {"username": user.username, "role": user.role}


@app.post("/api/auth/logout")
def logout(
    token: str = Depends(oauth), db: Session = Depends(get_db), user: User = Depends(current_user)
):
    from jose import jwt

    claims = jwt.get_unverified_claims(token)
    session = (
        db.query(AuthSession).filter_by(token_id=claims.get("jti"), username=user.username).first()
    )
    if session and session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)
        log(
            db,
            user.username,
            "auth.session_revoked",
            user.username,
            details={"token_id": session.token_id},
        )
        db.commit()
    return {"revoked": True}


@app.post("/api/auth/users", status_code=201)
def create_user(
    body: dict, db: Session = Depends(get_db), admin: User = Depends(allow("Administrator"))
):
    username, password, role = (
        body.get("username", ""),
        body.get("password", ""),
        body.get("role", "Auditor"),
    )
    roles = {"Administrator", "Fraud Analyst", "Investigator", "ML Engineer", "Auditor"}
    if len(username) < 3 or len(password) < 12 or role not in roles:
        raise HTTPException(422, "Username >=3, password >=12 and a supported role are required")
    if db.query(User).filter_by(username=username).first():
        raise HTTPException(409, "Username already exists")
    u = User(username=username, password_hash=hash_password(password), role=role)
    db.add(u)
    log(db, admin.username, "user.created", username, details={"role": role})
    db.commit()
    return {"username": u.username, "role": u.role}


@app.get("/api/auth/users")
def list_users(db: Session = Depends(get_db), admin: User = Depends(allow("Administrator"))):
    return [
        {"username": user.username, "role": user.role, "active": user.active}
        for user in db.query(User).order_by(User.username).all()
    ]


@app.patch("/api/auth/users/{username}")
def update_user(
    username: str,
    body: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(allow("Administrator")),
):
    roles = {"Administrator", "Fraud Analyst", "Investigator", "ML Engineer", "Auditor"}
    target = db.query(User).filter_by(username=username).first()
    if not target:
        raise HTTPException(404, "User not found")
    role, active = body.get("role"), body.get("active")
    if role is not None and role not in roles:
        raise HTTPException(422, "Unsupported role")
    if active is not None and not isinstance(active, bool):
        raise HTTPException(422, "Active must be a boolean")
    was_admin = target.role == "Administrator" and target.active
    will_be_admin = (role or target.role) == "Administrator" and (
        active if active is not None else target.active
    )
    if was_admin and not will_be_admin:
        other_admin = (
            db.query(User)
            .filter(User.role == "Administrator", User.active.is_(True), User.id != target.id)
            .first()
        )
        if not other_admin:
            raise HTTPException(409, "At least one active administrator must remain")
    if role is not None:
        target.role = role
    if active is not None:
        target.active = active
        if not active:
            now = datetime.now(timezone.utc)
            db.query(AuthSession).filter_by(username=username, revoked_at=None).update(
                {"revoked_at": now}
            )
    log(
        db,
        admin.username,
        "user.updated",
        username,
        details={"role": target.role, "active": target.active},
    )
    db.commit()
    return {"username": target.username, "role": target.role, "active": target.active}


@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return {
        "events": db.query(Event).count(),
        "incidents": db.query(Incident).count(),
        "open_incidents": db.query(Incident).filter(Incident.status.notin_(["Resolved", "False Positive"])).count(),
        "high_risk": db.query(Prediction).filter(Prediction.risk_score >= 0.6).count(),
        "avg_risk": db.query(func.avg(Prediction.risk_score)).scalar() or 0,
        "label_monitoring": label_monitoring_summary(db),
        "risk_distribution": [
            {"band": b, "count": db.query(Prediction).filter_by(risk_band=b).count()}
            for b in ["Low", "Medium", "High", "Critical"]
        ],
        "recent": [
            prediction_dict(p)
            for p in db.query(Prediction).order_by(Prediction.created_at.desc()).limit(8)
        ],
    }


@app.get("/api/events")
def events(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    subscriber_id: str | None = None,
    search: str | None = Query(default=None, alias="q", min_length=1, max_length=120),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    q = db.query(Event)
    if subscriber_id:
        q = q.filter_by(subscriber_id=subscriber_id)
    if search:
        pattern = f"%{search}%"
        q = q.filter(or_(Event.event_id.ilike(pattern), Event.subscriber_id.ilike(pattern), Event.event_type.ilike(pattern)))
    rows = q.order_by(Event.event_time.desc()).offset(offset).limit(limit).all()
    predictions = {
        prediction.event_id: prediction
        for prediction in db.query(Prediction).filter(Prediction.event_id.in_([row.event_id for row in rows])).all()
    } if rows else {}
    return [
        {
            **event_dict(e),
            "prediction": prediction_dict(predictions[e.event_id]) if e.event_id in predictions else None,
        }
        for e in rows
    ]


@app.get("/api/events/{event_id}/explanation")
def prediction_explanation(
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    event = db.query(Event).filter_by(event_id=event_id).first()
    prediction = db.query(Prediction).filter_by(event_id=event_id).first()
    if not event or not prediction:
        raise HTTPException(404, "Scored event not found")
    if prediction.explanation:
        return prediction.explanation
    run = db.query(ModelRun).filter_by(version=prediction.model_version).first()
    if not run:
        raise HTTPException(409, "The model version responsible for this prediction is unavailable")
    try:
        model = load_model_run(run)
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(503, "The prediction's model artifact cannot be loaded") from exc
    if model.get("version") != prediction.model_version or model.get("features") != FEATURES:
        raise HTTPException(409, "The model artifact version or feature schema does not match this prediction")

    prior = (
        db.query(Event)
        .filter(
            Event.subscriber_id == event.subscriber_id,
            Event.id != event.id,
            Event.event_time <= event.event_time,
        )
        .order_by(Event.event_time.desc())
        .limit(200)
        .all()
    )
    background = model.get("explain_background")
    if model.get("explain_background_feature_version", prediction.feature_version) != prediction.feature_version:
        raise HTTPException(409, "The model explanation background uses a different feature version")
    if background is None:
        dataset = db.query(DemoDataset).filter_by(version=run.dataset_version).first()
        background_rows = dataset.events if dataset else [e.model_dump(mode="json") for e in generate_events(200, 2026)]
        background = features(background_rows).sample(n=min(100, len(background_rows)), random_state=41).to_numpy()
    try:
        explanation = explain_prediction(
            model,
            event_dict(event),
            [event_dict(row) for row in reversed(prior)],
            background,
        )
    except (ValueError, TypeError, IndexError) as exc:
        raise HTTPException(422, f"Prediction explanation is unavailable: {exc}") from exc
    explanation["event_id"] = event_id
    explanation["prediction_id"] = prediction.id
    explanation["supervised_probability"] = prediction.probability
    prediction.explanation = explanation
    log(
        db,
        user.username,
        "prediction.explanation_generated",
        event_id,
        details={"model_version": prediction.model_version, "feature_version": prediction.feature_version},
    )
    db.commit()
    return explanation


@app.post("/api/events", status_code=201)
def ingest(
    data: EventIn,
    db: Session = Depends(get_db),
    user: User = Depends(allow("Administrator", "Fraud Analyst", "Investigator", "ML Engineer")),
):
    exists = db.query(Event).filter_by(event_id=data.event_id).first()
    if exists:
        p = db.query(Prediction).filter_by(event_id=data.event_id).first()
        return {
            "event": event_dict(exists),
            "prediction": prediction_dict(p) if p else None,
            "duplicate": True,
        }
    fields = data.model_dump(exclude={"contract_version", "fraud_label"})
    e = Event(**fields, fraud_label=data.fraud_label)
    db.add(e)
    db.flush()
    p = score_event(db, e, user, app.state.model)
    db.commit()
    return {"event": event_dict(e), "prediction": prediction_dict(p), "duplicate": False}


@app.post("/api/events/upload-csv", status_code=201)
async def upload_events_csv(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(allow("Administrator", "Fraud Analyst", "Investigator", "ML Engineer")),
):
    """Validate a bounded CSV atomically, then batch-score and persist its events."""
    try:
        content_length = int(request.headers.get("content-length", "0") or 0)
    except ValueError as exc:
        raise HTTPException(400, "Invalid content-length") from exc
    if content_length > 25_000_000:
        raise HTTPException(413, "CSV upload exceeds the 25 MB limit")
    raw = await request.body()
    if len(raw) > 25_000_000:
        raise HTTPException(413, "CSV upload exceeds the 25 MB limit")
    try:
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        required = {"event_id", "event_type", "event_time", "subscriber_id"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError("CSV requires event_id, event_type, event_time and subscriber_id columns")
        validated = []
        for line_number, source in enumerate(reader, start=2):
            if line_number > 5002:
                raise ValueError("CSV upload is limited to 5000 data rows")
            values = {key: value.strip() if value is not None else None for key, value in source.items()}
            for field in ("latitude", "longitude", "duration_seconds", "message_count", "fraud_label"):
                if values.get(field) == "":
                    values[field] = None
                elif values.get(field) is not None:
                    values[field] = int(values[field]) if field in {"duration_seconds", "message_count", "fraud_label"} else float(values[field])
            for field in ("is_international", "is_roaming"):
                if values.get(field) in {None, ""}:
                    values[field] = None
                elif values.get(field, "").lower() in {"true", "1", "yes"}:
                    values[field] = True
                elif values.get(field, "").lower() in {"false", "0", "no"}:
                    values[field] = False
                else:
                    raise ValueError(f"row {line_number}: {field} must be true or false")
            for field in ("source_token", "destination_token", "sim_id", "device_id", "network_token", "location_token", "scenario_label", "call_direction", "call_status", "auth_outcome"):
                if values.get(field) == "":
                    values[field] = None
            try:
                validated.append(EventIn.model_validate(values))
            except Exception as exc:
                raise ValueError(f"row {line_number}: {exc}") from exc
        if not validated:
            raise ValueError("CSV contains no event rows")
    except (UnicodeDecodeError, csv.Error, ValueError, TypeError) as exc:
        raise HTTPException(422, f"Invalid CSV: {exc}") from exc

    validated.sort(key=lambda event: event.event_time)
    identifiers = [event.event_id for event in validated]
    if len(set(identifiers)) != len(identifiers):
        raise HTTPException(422, "CSV contains duplicate event_id values")
    existing_ids = {event_id for (event_id,) in db.query(Event.event_id).filter(Event.event_id.in_(identifiers)).all()}
    new_events = [event for event in validated if event.event_id not in existing_ids]
    if not new_events:
        return {"created": 0, "duplicates": len(validated), "predictions": 0}

    max_time = max(event.event_time for event in new_events)
    subscriber_ids = {event.subscriber_id for event in new_events}
    ranked = (
        db.query(
            Event.id.label("event_pk"),
            func.row_number().over(partition_by=Event.subscriber_id, order_by=Event.event_time.desc()).label("position"),
        )
        .filter(Event.subscriber_id.in_(subscriber_ids), Event.event_time <= max_time)
        .subquery()
    )
    context_rows = db.query(Event).join(ranked, Event.id == ranked.c.event_pk).filter(ranked.c.position <= 200).all()
    related_filters = [
        getattr(Event, field).in_({event.model_dump().get(field) for event in new_events if event.model_dump().get(field)})
        for field in ("device_id", "network_token", "sim_id")
    ]
    if related_filters:
        related = db.query(Event).filter(
            Event.event_time <= max_time,
            Event.subscriber_id.not_in(subscriber_ids),
            or_(*related_filters),
        ).order_by(Event.event_time.desc()).limit(5000).all()
        context_rows.extend(related)
    context_rows = list({event.id: event for event in context_rows}.values())
    context = [event_dict(event) for event in context_rows]
    rows = [event.model_dump(mode="json", exclude={"contract_version"}) for event in new_events]
    new_ids = {event.event_id for event in new_events}
    combined = context + rows
    ordered = sorted(enumerate(combined), key=lambda item: (item[1]["event_time"], item[0]))
    ordered_rows = [row for _, row in ordered]
    feature_state = FeatureState()
    combined_features = feature_state.transform(ordered_rows)
    new_positions = [position for position, (_, row) in enumerate(ordered) if row["event_id"] in new_ids]
    new_rows_ordered = [ordered_rows[position] for position in new_positions]
    new_features = combined_features.iloc[new_positions].reset_index(drop=True)

    state = BatchScoringState()
    state.seed_context(context)
    active_version = _mlops_state(db)
    active_row = db.query(ModelRun).filter_by(version=active_version).first()
    champion = load_model_run(active_row) if active_row else app.state.model
    if champion.get("version") != active_version:
        raise HTTPException(503, "The selected champion model could not be loaded")
    serving = current_serving_config(db)
    challenger = None
    if serving.get("mode") in {"shadow", "canary"} and serving.get("challenger_version"):
        candidate = db.query(ModelRun).filter_by(version=serving["challenger_version"]).first()
        if candidate:
            try:
                challenger = load_model_run(candidate)
            except Exception as exc:
                log(db, "system", "model.challenger_failed", candidate.version,
                    reason=str(exc)[:250], details={"champion_retained": True, "csv_upload": True})
                serving = {"mode": "champion"}
    scored = state.score(new_rows_ordered, new_features, champion, challenger, serving, current_scenario_config(db))

    event_objects = []
    for event in new_events:
        fields = event.model_dump(exclude={"contract_version"})
        event_objects.append(Event(**fields))
    db.add_all(event_objects)
    db.flush()
    prediction_objects = [Prediction(
        event_id=result["event_id"], model_version=result["model_version"],
        feature_version=result["feature_version"],
        policy_version=settings.risk_policy_version,
        probability=result["probability"], anomaly_score=result["anomaly_score"],
        graph_score=result["graph_score"], rule_score=result["rule_score"],
        risk_score=result["risk_score"], risk_band=result["risk_band"], evidence=result["evidence"],
    ) for result in scored]
    db.add_all(prediction_objects)
    db.flush()
    prediction_by_event = {prediction.event_id: prediction for prediction in prediction_objects}
    db.add_all([
        ModelObservation(
            prediction_id=prediction_by_event[result["event_id"]].id,
            model_version=model_version, serving_role=role, probability=probability,
            predicted_label=int(probability >= 0.5),
        )
        for result in scored for model_version, role, probability in result["observations"]
    ])
    event_by_id = {event.event_id: event for event in event_objects}
    db.add_all([
        Incident(
            prediction_id=prediction_by_event[result["event_id"]].id,
            subscriber_id=event_by_id[result["event_id"]].subscriber_id,
            title=f"Elevated synthetic risk — {event_by_id[result['event_id']].event_type}",
            severity=result["risk_band"],
        )
        for result in scored if result["risk_score"] >= settings.incident_risk_threshold
    ])
    log(db, user.username, "event.csv_batch_ingested", f"rows:{len(new_events)}",
        details={"created": len(new_events), "duplicates": len(validated) - len(new_events)})
    db.commit()
    return {"created": len(new_events), "duplicates": len(validated) - len(new_events),
            "predictions": len(prediction_objects), "dataset_version": None}


@app.post("/api/scenarios/generate")
def generate(
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(allow("Administrator", "Fraud Analyst", "Investigator", "ML Engineer")),
):
    try:
        generated = generate_events(int(body.get("count", 140)), int(body.get("seed", 42)))
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc))
    created = 0
    for item in generated:
        if db.query(Event).filter_by(event_id=item.event_id).first():
            continue
        values = item.model_dump(exclude={"contract_version", "fraud_label"})
        e = Event(**values, fraud_label=item.fraud_label)
        db.add(e)
        db.flush()
        score_event(db, e, user, app.state.model)
        created += 1
    log(
        db,
        user.username,
        "scenario.generated",
        f"seed:{body.get('seed', 42)}",
        details={"count": created},
    )
    db.commit()
    return {
        "generated": created,
        "seed": int(body.get("seed", 42)),
        "dataset_version": "scenario-v1",
    }


@app.get("/api/incidents")
def incidents(
    status: str | None = None,
    severity: str | None = None,
    assigned_to: str | None = None,
    q: str | None = Query(default=None, min_length=1, max_length=120),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    query = db.query(Incident)
    if status:
        query = query.filter_by(status=status)
    if severity:
        query = query.filter_by(severity=severity)
    if assigned_to:
        query = query.filter_by(assigned_to=assigned_to)
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            or_(Incident.title.ilike(pattern), Incident.subscriber_id.ilike(pattern))
        )
    rows = query.order_by(Incident.created_at.desc()).offset(offset).limit(limit).all()
    if not rows:
        return []
    incident_ids = [incident.id for incident in rows]
    prediction_ids = [incident.prediction_id for incident in rows]
    predictions = {prediction.id: prediction for prediction in db.query(Prediction).filter(Prediction.id.in_(prediction_ids)).all()}
    notes_by_incident = defaultdict(list)
    for note in db.query(Note).filter(Note.incident_id.in_(incident_ids)).order_by(Note.created_at).all():
        notes_by_incident[note.incident_id].append(
            {"author": note.author, "body": note.body, "created_at": note.created_at.isoformat()}
        )
    history_ranked = (
        db.query(
            AuditLog.id.label("audit_id"),
            func.row_number().over(partition_by=AuditLog.target, order_by=AuditLog.created_at.desc()).label("position"),
        )
        .filter(AuditLog.target.in_([str(incident_id) for incident_id in incident_ids]), AuditLog.action.like("incident.%"))
        .subquery()
    )
    history_by_incident = defaultdict(list)
    history_rows = (
        db.query(AuditLog).join(history_ranked, AuditLog.id == history_ranked.c.audit_id)
        .filter(history_ranked.c.position <= 50).all()
    )
    for entry in history_rows:
        history_by_incident[int(entry.target)].append({
            "actor": entry.actor, "action": entry.action, "reason": entry.reason,
            "details": entry.details, "created_at": entry.created_at.isoformat(),
        })
    return [
        {
            "id": i.id,
            "subscriber_id": i.subscriber_id,
            "title": i.title,
            "status": i.status,
            "severity": i.severity,
            "assigned_to": i.assigned_to,
            "created_at": i.created_at.isoformat(),
            "resolution_outcome": i.resolution_outcome,
            "resolution_reason": i.resolution_reason,
            "resolved_by": i.resolved_by,
            "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
            "prediction": prediction_dict(predictions[i.prediction_id]),
            "notes": notes_by_incident[i.id],
            "history": history_by_incident[i.id],
        }
        for i in rows
    ]


@app.patch("/api/incidents/{incident_id}")
def update_incident(
    incident_id: int,
    data: IncidentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(allow("Administrator", "Fraud Analyst", "Investigator")),
):
    i = db.get(Incident, incident_id)
    if not i:
        raise HTTPException(404, "Incident not found")
    if data.status and data.status not in {
        "New",
        "Investigating",
        "Escalated",
        "Resolved",
        "False Positive",
    }:
        raise HTTPException(422, "Invalid status")
    before = {"status": i.status, "assigned_to": i.assigned_to}
    final_statuses = {"Resolved", "False Positive"}
    outcomes = {"confirmed_fraud", "legitimate", "inconclusive", "duplicate"}
    if data.resolution_outcome is not None and data.resolution_outcome not in outcomes:
        raise HTTPException(422, "Invalid resolution outcome")
    if data.status:
        if data.status in final_statuses and not data.resolution_outcome:
            raise HTTPException(422, "A resolution outcome is required for a final status")
        if data.status == "False Positive" and data.resolution_outcome != "legitimate":
            raise HTTPException(422, "False Positive requires the legitimate outcome")
        i.status = data.status
    if data.assigned_to is not None:
        assignee_name = data.assigned_to.strip()
        if assignee_name:
            assignee = db.query(User).filter_by(username=assignee_name, active=True).first()
            if not assignee or assignee.role not in {"Fraud Analyst", "Investigator"}:
                raise HTTPException(422, "Assignee must be an active fraud analyst or investigator")
            i.assigned_to = assignee_name
        else:
            i.assigned_to = None
    if data.status in final_statuses:
        i.resolution_outcome = data.resolution_outcome
        i.resolution_reason = data.reason
        i.resolved_by = user.username
        i.resolved_at = datetime.now(timezone.utc)
    elif data.status and data.status not in final_statuses:
        i.resolution_outcome = None
        i.resolution_reason = None
        i.resolved_by = None
        i.resolved_at = None
    log(
        db,
        user.username,
        "incident.updated",
        str(i.id),
        data.reason,
        {
            "from": before,
            "to": {
                "status": i.status,
                "assigned_to": i.assigned_to,
                "resolution_outcome": i.resolution_outcome,
                "resolution_reason": i.resolution_reason,
            },
        },
    )
    db.commit()
    return {
        "id": i.id,
        "status": i.status,
        "assigned_to": i.assigned_to,
        "resolution_outcome": i.resolution_outcome,
        "resolved_by": i.resolved_by,
        "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
    }


@app.post("/api/incidents/{incident_id}/notes", status_code=201)
def add_note(
    incident_id: int,
    data: NoteIn,
    db: Session = Depends(get_db),
    user: User = Depends(allow("Administrator", "Fraud Analyst", "Investigator")),
):
    if not db.get(Incident, incident_id):
        raise HTTPException(404, "Incident not found")
    n = Note(incident_id=incident_id, author=user.username, body=data.body)
    db.add(n)
    log(db, user.username, "incident.note_added", str(incident_id))
    db.commit()
    return {"author": n.author, "body": n.body, "created_at": n.created_at.isoformat()}


@app.post("/api/incidents/{incident_id}/actions", status_code=201)
def action(
    incident_id: int,
    data: ActionIn,
    db: Session = Depends(get_db),
    user: User = Depends(allow("Administrator", "Investigator")),
):
    i = db.get(Incident, incident_id)
    if not i:
        raise HTTPException(404, "Incident not found")
    if data.action not in {
        "monitor",
        "protect_simulated_account",
        "flag_device",
        "watchlist",
        "escalate",
    }:
        raise HTTPException(422, "Unsupported simulated action")
    log(
        db,
        user.username,
        f"simulated.{data.action}",
        i.subscriber_id,
        data.reason,
        {"incident_id": i.id, "simulation_only": True},
    )
    record = ResponseAction(
        incident_id=i.id, action=data.action, actor=user.username, reason=data.reason
    )
    db.add(record)
    db.commit()
    return {"id": record.id, "recorded": True, "simulation_only": True, "action": data.action}


@app.post("/api/actions/{action_id}/reverse", status_code=201)
def reverse_action(
    action_id: int,
    data: ActionIn,
    db: Session = Depends(get_db),
    user: User = Depends(allow("Administrator", "Investigator")),
):
    original = db.get(ResponseAction, action_id)
    if not original:
        raise HTTPException(404, "Simulated action not found")
    if db.query(ResponseAction).filter_by(reverses_id=original.id).first():
        raise HTTPException(409, "Action already has a recorded reversal")
    reversal = ResponseAction(
        incident_id=original.incident_id,
        action=f"reverse:{original.action}",
        actor=user.username,
        reason=data.reason,
        reverses_id=original.id,
    )
    db.add(reversal)
    db.flush()
    log(
        db,
        user.username,
        "simulated.action_reversed",
        str(original.id),
        data.reason,
        {"reversal_id": reversal.id, "simulation_only": True},
    )
    db.commit()
    return {
        "id": reversal.id,
        "reverses_id": original.id,
        "recorded": True,
        "simulation_only": True,
    }


@app.get("/api/models")
def models(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [
        {
            "version": m.version,
            "algorithm": m.algorithm,
            "dataset_version": m.dataset_version,
            "mlflow_run_id": m.mlflow_run_id,
            "metrics": m.metrics,
            "created_at": m.created_at.isoformat(),
        }
        for m in db.query(ModelRun).order_by(ModelRun.created_at.desc()).all()
    ]


@app.post("/api/models/train")
def train(
    db: Session = Depends(get_db), user: User = Depends(allow("Administrator", "ML Engineer"))
):
    result = train_model()
    row = db.query(ModelRun).filter_by(version=result["version"]).first()
    if not row:
        row = ModelRun(
            version=result["version"],
            algorithm=result["algorithm"],
            dataset_version=result.get("dataset_version", "scenario-v1-seed-2026"),
            metrics=result["metrics"],
            artifact_path=result["artifact_path"],
        )
        db.add(row)
    run_id = None
    try:
        run_id = track_training_run(result)
        row.mlflow_run_id = run_id
    except Exception as exc:
        log(db, user.username, "mlflow.unavailable", result["version"], reason=str(exc)[:500])
    log(db, user.username, "model.trained", row.version, details=result["metrics"])
    db.commit()
    return {
        "version": row.version,
        "metrics": row.metrics,
        "mlflow_run_id": run_id,
        "note": result["metrics"]["evaluation_note"],
    }


def _record(db: Session, kind: str, version: str, payload: dict, actor: str):
    row = MLOpsRecord(kind=kind, version=version, payload=payload, created_by=actor)
    db.add(row)
    db.flush()
    return row


def _mlops_state(db: Session):
    active = (
        db.query(MLOpsRecord).filter_by(kind="active_model").order_by(MLOpsRecord.id.desc()).first()
    )
    return active.version if active else app.state.model.get("version")


@app.get("/api/mlops")
def mlops_summary(db: Session = Depends(get_db), user: User = Depends(current_user)):
    registry_versions = []
    registry_available = False
    try:
        from mlflow.tracking import MlflowClient

        registry_versions = [
            {
                "name": version.name,
                "version": version.version,
                "run_id": version.run_id,
                "status": version.status,
                "created_at_ms": version.creation_timestamp,
            }
            for version in MlflowClient().search_model_versions("name='TeleGuardSyntheticFraud'")
        ]
        registry_available = True
    except Exception:
        # The API remains usable when the optional tracking service is unavailable.
        registry_available = False
    return {
        "active_model": _mlops_state(db),
        "serving_config": current_serving_config(db),
        "scenario_config": current_scenario_config(db),
        "label_monitoring": label_monitoring_summary(db),
        "mlflow_registry_available": registry_available,
        "mlflow_registry": registry_versions,
        "models": [
            {
                "version": m.version,
                "algorithm": m.algorithm,
                "dataset_version": m.dataset_version,
                "metrics": m.metrics,
                "created_at": m.created_at.isoformat(),
            }
            for m in db.query(ModelRun).order_by(ModelRun.created_at.desc()).all()
        ],
        "datasets": [
            {
                "version": d.version,
                "kind": d.kind,
                "seed": d.seed,
                "rows": len(d.events),
                "metadata": d.metadata_json,
                "created_at": d.created_at.isoformat(),
            }
            for d in db.query(DemoDataset).order_by(DemoDataset.created_at.desc()).all()
        ],
        "operational_datasets": [
            {
                "version": d.version,
                "kind": d.kind,
                "generator_version": d.generator_version,
                "seed": d.seed,
                "rows": d.row_count,
                "target_rows": d.target_rows,
                "status": d.status,
                "metadata": d.metadata_json,
                "created_by": d.created_by,
                "created_at": d.created_at.isoformat(),
                "completed_at": d.completed_at.isoformat() if d.completed_at else None,
            }
            for d in db.query(DatasetVersion).order_by(DatasetVersion.created_at.desc()).all()
        ],
        "jobs": [
            {
                "id": j.id, "kind": j.kind, "status": j.status,
                "progress_current": j.progress_current, "progress_total": j.progress_total,
                "result": j.result, "error": j.error,
                "requested_by": j.requested_by, "created_at": j.created_at.isoformat(),
                "updated_at": j.updated_at.isoformat(),
            }
            for j in db.query(MLOpsJob).order_by(MLOpsJob.created_at.desc()).limit(20).all()
        ],
        "records": [
            {
                "kind": r.kind,
                "version": r.version,
                "payload": r.payload,
                "created_by": r.created_by,
                "created_at": r.created_at.isoformat(),
            }
            for r in db.query(MLOpsRecord).order_by(MLOpsRecord.created_at.desc()).limit(100).all()
        ],
    }


@app.post("/api/datasets/seed", status_code=status.HTTP_202_ACCEPTED)
def seed_initial_dataset(
    body: SeedDatasetIn,
    db: Session = Depends(get_db),
    user: User = Depends(allow("Administrator")),
):
    version = dataset_version_for(body.count, body.seed)
    dataset = db.get(DatasetVersion, version)
    if dataset and dataset.status == "ready" and dataset.row_count == body.count:
        completed = next((job for job in db.query(MLOpsJob)
                          .filter_by(kind="seed_dataset", status="succeeded")
                          .order_by(MLOpsJob.created_at.desc()).limit(50).all()
                          if job.arguments.get("dataset_version") == version), None)
        if completed:
            return {"job_id": completed.id, "status": completed.status,
                    "dataset_version": version, "already_ready": True}
    existing = db.query(MLOpsJob).filter(
        MLOpsJob.kind == "seed_dataset",
        MLOpsJob.status.in_(["queued", "running", "paused", "stopping"]),
    ).order_by(MLOpsJob.created_at.desc()).all()
    for job in existing:
        if job.arguments.get("dataset_version") == version:
            return {"job_id": job.id, "status": job.status, "dataset_version": version}
    job = queue_job(
        db,
        "seed_dataset",
        user.username,
        {"count": body.count, "seed": body.seed, "dataset_version": version, "initial": True},
    )
    job.progress_total = body.count
    db.commit()
    return {"job_id": job.id, "status": job.status, "dataset_version": version,
            "rows": body.count, "minimum_rows": MIN_INITIAL_ROWS,
            "maximum_rows": MAX_INITIAL_ROWS}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    job = db.get(MLOpsJob, job_id)
    if not job or (job.requested_by != user.username and user.role != "Administrator"):
        raise HTTPException(404, "Job not found")
    return {
        "id": job.id, "kind": job.kind, "status": job.status,
        "progress_current": job.progress_current, "progress_total": job.progress_total,
        "result": job.result, "error": job.error,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "updated_at": job.updated_at.isoformat(),
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


@app.post("/api/jobs/{job_id}/control")
def control_job(
    job_id: str, body: JobControlIn, db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    job = db.get(MLOpsJob, job_id)
    if not job or (job.requested_by != user.username and user.role != "Administrator"):
        raise HTTPException(404, "Job not found")
    if (job.status == "running" and job.progress_total > 0
            and job.progress_current >= job.progress_total and body.action in {"pause", "stop"}):
        raise HTTPException(409, "Dataset generation is complete; model training and registration are not interruptible")
    transitions = {
        "pause": {"queued": "paused", "running": "paused"},
        "resume": {"paused": "queued"},
        "stop": {"queued": "stopped", "paused": "stopped", "running": "stopping"},
    }
    new_status = transitions[body.action].get(job.status)
    if not new_status:
        raise HTTPException(409, f"Cannot {body.action} a {job.status} job")
    job.status = new_status
    job.updated_at = datetime.now(timezone.utc)
    if new_status == "stopped":
        job.finished_at = job.updated_at
        dataset_version = job.arguments.get("dataset_version")
        dataset = db.get(DatasetVersion, dataset_version) if dataset_version else None
        if dataset and dataset.status != "ready":
            dataset.status = "stopped"
    log(db, user.username, f"mlops.job_{body.action}", job.id,
        details={"status": new_status, "progress": job.progress_current})
    db.commit()
    return {"id": job.id, "status": job.status, "progress_current": job.progress_current}


def label_monitoring_summary(db):
    labels = db.query(Prediction).filter(Prediction.ground_truth_label.is_not(None)).count()
    pending = db.query(Prediction).filter(Prediction.ground_truth_label.is_(None)).count()
    result = {}
    aggregated = db.query(
        ModelObservation.model_version,
        func.count(ModelObservation.id).label("predictions"),
        func.sum(case((ModelObservation.outcome_label.is_not(None), 1), else_=0)).label("evaluated"),
        func.sum(case((and_(ModelObservation.outcome_label == 1, ModelObservation.predicted_label == 1), 1), else_=0)).label("tp"),
        func.sum(case((and_(ModelObservation.outcome_label == 0, ModelObservation.predicted_label == 1), 1), else_=0)).label("fp"),
        func.sum(case((and_(ModelObservation.outcome_label == 0, ModelObservation.predicted_label == 0), 1), else_=0)).label("tn"),
        func.sum(case((and_(ModelObservation.outcome_label == 1, ModelObservation.predicted_label == 0), 1), else_=0)).label("fn"),
        func.sum(case((ModelObservation.outcome_label.is_not(None), (ModelObservation.probability - ModelObservation.outcome_label) * (ModelObservation.probability - ModelObservation.outcome_label)), else_=0.0)).label("brier_sum"),
    ).group_by(ModelObservation.model_version).all()
    degradation_alerts = []
    for row in aggregated:
        version = row.model_version
        stats = {
            "predictions": int(row.predictions or 0),
            "evaluated": int(row.evaluated or 0),
            "tp": int(row.tp or 0), "fp": int(row.fp or 0),
            "tn": int(row.tn or 0), "fn": int(row.fn or 0),
            "brier_sum": float(row.brier_sum or 0.0),
        }
        result[version] = stats
        stats["precision"] = stats["tp"] / max(stats["tp"] + stats["fp"], 1)
        stats["recall"] = stats["tp"] / max(stats["tp"] + stats["fn"], 1)
        stats["false_positive_rate"] = stats["fp"] / max(stats["fp"] + stats["tn"], 1)
        stats["brier_score"] = stats["brier_sum"] / max(stats["evaluated"], 1) if stats["evaluated"] else None
        labeled = db.query(ModelObservation.outcome_label, ModelObservation.probability).filter(
            ModelObservation.model_version == version,
            ModelObservation.outcome_label.is_not(None),
        ).yield_per(10000)
        label_values, probability_values = [], []
        for actual, probability in labeled:
            label_values.append(actual)
            probability_values.append(probability)
        stats["pr_auc"] = (
            float(average_precision_score(label_values, probability_values))
            if len(set(label_values)) == 2 else None
        )
        recent_desc = db.query(ModelObservation).filter(
            ModelObservation.model_version == version,
            ModelObservation.outcome_label.is_not(None),
        ).order_by(func.coalesce(ModelObservation.evaluated_at, ModelObservation.created_at).desc()).limit(40).all()
        recent = list(reversed(recent_desc))
        if len(recent) >= 40:
            prior_metrics = _observation_rates(recent[:20])
            recent_metrics = _observation_rates(recent[20:])
            stats["rolling"] = {"previous_20_recall": prior_metrics["recall"], "recent_20_recall": recent_metrics["recall"], "previous_20_fpr": prior_metrics["false_positive_rate"], "recent_20_fpr": recent_metrics["false_positive_rate"]}
            if prior_metrics["recall"] - recent_metrics["recall"] >= 0.15 or recent_metrics["false_positive_rate"] - prior_metrics["false_positive_rate"] >= 0.10:
                degradation_alerts.append({"model_version": version, **stats["rolling"], "action": "Review recent labeled cases, compare the approved champion, and roll back or retrain only after administrator review."})
        del stats["brier_sum"]
    return {"pending_labels": pending, "received_labels": labels, "models": result,
            "alert": bool(degradation_alerts), "degradation_alerts": degradation_alerts,
            "alert_policy": "Compare the most recent 20 delayed labels with the prior 20 for each model; alert on recall decline >= 0.15 or false-positive-rate increase >= 0.10. Synthetic thresholds; review case context before action."}


def _observation_rates(rows):
    tp = sum(o.outcome_label == 1 and o.predicted_label == 1 for o in rows)
    fp = sum(o.outcome_label == 0 and o.predicted_label == 1 for o in rows)
    tn = sum(o.outcome_label == 0 and o.predicted_label == 0 for o in rows)
    fn = sum(o.outcome_label == 1 and o.predicted_label == 0 for o in rows)
    return {"recall": tp / max(tp + fn, 1), "false_positive_rate": fp / max(fp + tn, 1)}


@app.post("/api/predictions/{event_id}/label")
def ingest_delayed_label(event_id: str, body: dict, db: Session = Depends(get_db), user: User = Depends(allow("Administrator", "Fraud Analyst", "Investigator", "ML Engineer"))):
    label = body.get("label")
    source = str(body.get("source", "analyst"))[:80]
    if label not in (0, 1):
        raise HTTPException(422, "label must be 0 or 1")
    prediction = db.query(Prediction).with_for_update().join(Event, Prediction.event_id == Event.event_id).filter(Event.event_id == event_id).first()
    if not prediction:
        raise HTTPException(404, "Prediction not found")
    if prediction.ground_truth_label is not None:
        raise HTTPException(409, "A ground-truth label is already recorded; labels are immutable")
    prediction.ground_truth_label = label
    prediction.label_source = source
    prediction.label_received_at = datetime.now(timezone.utc)
    for observation in db.query(ModelObservation).filter_by(prediction_id=prediction.id).all():
        observation.outcome_label = label
        observation.evaluated_at = prediction.label_received_at
    log(db, user.username, "prediction.label_received", event_id, details={"label": label, "source": source, "observations_evaluated": len(db.query(ModelObservation).filter_by(prediction_id=prediction.id).all())})
    db.commit()
    return {"event_id": event_id, "label": label, "status": "evaluated", "monitoring": label_monitoring_summary(db)}


@app.post("/api/mlops/serving")
def configure_serving(body: dict, db: Session = Depends(get_db), user: User = Depends(allow("Administrator"))):
    mode = body.get("mode")
    version = body.get("challenger_version")
    percent = body.get("canary_percent", 0)
    if mode not in {"champion", "shadow", "canary"} or not isinstance(percent, int) or not 0 <= percent <= 100:
        raise HTTPException(422, "mode must be champion, shadow or canary and canary_percent must be 0..100")
    if mode in {"shadow", "canary"}:
        candidate = db.query(ModelRun).filter_by(version=version).first()
        if not candidate or version == _mlops_state(db):
            raise HTTPException(422, "A persisted non-champion challenger_version is required")
        comparison = next((row for row in db.query(MLOpsRecord).filter_by(kind="comparison").order_by(MLOpsRecord.id.desc()).all() if row.payload.get("challenger_version") == version), None)
        if not comparison or comparison.payload.get("champion_version") != _mlops_state(db) or not comparison.payload.get("passed"):
            raise HTTPException(409, "Compare this challenger against the current champion and pass promotion gates before shadow/canary serving")
        try:
            loaded = load_model_run(candidate)
            if loaded.get("version") != version:
                raise ValueError("artifact version mismatch")
        except Exception as exc:
            raise HTTPException(422, "Challenger artifact failed validation; serving configuration unchanged") from exc
    config = {"mode": mode, "challenger_version": version if mode in {"shadow", "canary"} else None, "canary_percent": percent if mode == "canary" else 0}
    _record(db, "serving_config", f"serving-{uuid4().hex[:12]}", config, user.username)
    log(db, user.username, "model.serving_configured", config["challenger_version"] or _mlops_state(db), details=config)
    db.commit()
    return config


@app.get("/api/mlops/monitoring")
def get_monitoring(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return label_monitoring_summary(db)


@app.post("/api/mlops/scenarios")
def configure_scenarios(body: dict, db: Session = Depends(get_db), user: User = Depends(allow("Administrator"))):
    defaults = current_scenario_config(db)
    try:
        defaults.update({k: body[k] for k in defaults if k in body})
        if "scenario_rules" in body:
            defaults["scenario_rules"] = body["scenario_rules"]
        if not isinstance(defaults["scenario_rules"], dict) or len(defaults["scenario_rules"]) > 50 or any(not isinstance(v, dict) or set(v) - {"event_type", "location_token", "description"} for v in defaults["scenario_rules"].values()):
            raise ValueError
        if any(v.get("event_type") and v["event_type"] not in {"CALL", "SMS", "SIM_CHANGE", "DEVICE_CHANGE", "ACCOUNT_ACTIVITY", "OTP_REQUEST", "AUTHENTICATION", "NETWORK_ACTIVITY", "LOCATION"} for v in defaults["scenario_rules"].values()):
            raise ValueError
        if any(not (v.get("event_type") or v.get("location_token")) or (v.get("location_token") and not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]{2,63}", v["location_token"])) or len(str(v.get("description", ""))) > 240 for v in defaults["scenario_rules"].values()):
            raise ValueError
        if not (50 <= float(defaults["max_speed_kmh"]) <= 1500 and 1 <= int(defaults["impossible_travel_minutes"]) <= 1440 and 0 <= float(defaults["risk_weight"]) <= 1 and 1 <= int(defaults["unusual_location_min_history"]) <= 100):
            raise ValueError
    except (TypeError, ValueError):
        raise HTTPException(422, "Invalid scenario thresholds")
    _record(db, "scenario_config", f"scenario-{uuid4().hex[:12]}", defaults, user.username)
    log(db, user.username, "scenario.configured", "location-travel", details=defaults)
    db.commit()
    return defaults


@app.post("/api/mlops/initialize")
def mlops_initialize(db: Session = Depends(get_db), user: User = Depends(allow("Administrator"))):
    baseline = db.query(DemoDataset).filter_by(kind="baseline").first()
    if not baseline:
        events = [e.model_dump(mode="json") for e in generate_events(1400, 2026)]
        baseline = DemoDataset(
            version="baseline-v1-seed-2026",
            kind="baseline",
            seed=2026,
            events=events,
            metadata_json={"generator": "synthetic-v1", "rows": len(events)},
        )
        db.add(baseline)
    if not db.query(MLOpsRecord).filter_by(kind="active_model").first():
        _record(
            db,
            "active_model",
            app.state.model["version"],
            {"reason": "baseline initialization"},
            user.username,
        )
        _record(
            db,
            "approved_model",
            app.state.model["version"],
            {"reason": "verified startup baseline"},
            user.username,
        )
    db.commit()
    return {"baseline_dataset": baseline.version, "active_model": _mlops_state(db)}


@app.post("/api/mlops/drift/simulate")
def simulate_drift(
    body: dict | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(allow("Administrator")),
):
    if not db.query(DemoDataset).filter_by(kind="baseline").first():
        raise HTTPException(409, "Initialize the baseline before simulating drift")
    seed = int((body or {}).get("seed", 731))
    events = [e.model_dump(mode="json") for e in generate_events(1400, seed)]
    rng = np.random.default_rng(seed)
    for event in events:
        if event["event_type"] == "CALL" and event.get("duration_seconds") is not None:
            event["duration_seconds"] = min(3600, int(event["duration_seconds"] * 1.8))
        if rng.random() < 0.55:
            event["network_token"] = f"drift_net_{int(rng.integers(0, 12)):02d}"
        event["location_token"] = f"drift_region_{int(rng.integers(0, 3)):02d}"
    version = f"drift-v1-seed-{seed}-{uuid4().hex[:8]}"
    row = DemoDataset(
        version=version,
        kind="drift",
        seed=seed,
        events=events,
        metadata_json={
            "modified_features": ["duration_seconds", "network_token", "location_token"],
            "description": "Longer calls and concentrated synthetic network/location tokens; labels retained.",
        },
    )
    db.add(row)
    log(db, user.username, "mlops.drift_simulated", version, details=row.metadata_json)
    db.commit()
    return {"version": version, "rows": len(events), **row.metadata_json}


def _psi(reference: list, current: list, bins: int = 10):
    a = np.asarray(reference, dtype=float)
    b = np.asarray(current, dtype=float)
    edges = np.unique(np.quantile(a, np.linspace(0, 1, bins + 1)))
    if len(edges) < 2:
        edges = np.array([a.min() - 0.5, a.max() + 0.5])
    edges[0], edges[-1] = -np.inf, np.inf
    ac, _ = np.histogram(a, bins=edges)
    bc, _ = np.histogram(b, bins=edges)
    ap = np.maximum(ac / max(len(a), 1), 1e-4)
    bp = np.maximum(bc / max(len(b), 1), 1e-4)
    return (
        float(np.sum((bp - ap) * np.log(bp / ap))),
        ac.tolist(),
        bc.tolist(),
        edges[1:-1].tolist(),
    )


@app.post("/api/mlops/drift/detect")
def detect_drift(
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(allow("Administrator", "ML Engineer")),
):
    reference = db.query(DemoDataset).filter_by(version=body.get("reference_version")).first()
    current = db.query(DemoDataset).filter_by(version=body.get("current_version")).first()
    if not reference or not current:
        raise HTTPException(404, "Reference or current dataset version not found")

    def vals(rows, field):
        if field == "call_duration_seconds":
            return [
                e["duration_seconds"]
                for e in rows
                if e["event_type"] == "CALL" and e.get("duration_seconds") is not None
            ]
        if field == "event_hour_utc":
            return [
                datetime.fromisoformat(e["event_time"].replace("Z", "+00:00")).hour for e in rows
            ]
        return [
            sum(e.get(field) == x for e in rows) / max(len(rows), 1)
            for x in sorted({e.get(field) for e in rows})
        ]

    features_out = []
    for feature in ("call_duration_seconds", "event_hour_utc"):
        v, ref_counts, cur_counts, cuts = _psi(
            vals(reference.events, feature), vals(current.events, feature)
        )
        features_out.append(
            {
                "feature": feature,
                "psi": v,
                "threshold": 0.2,
                "drifted": v >= 0.2,
                "reference_distribution": ref_counts,
                "current_distribution": cur_counts,
                "bin_edges": cuts,
            }
        )
    # Categorical token concentration is measured through PSI over shared top categories plus other.
    for field in ("network_token", "location_token"):
        rv = [e.get(field, "") for e in reference.events]
        cv = [e.get(field, "") for e in current.events]
        cats = sorted(set(rv) | set(cv))
        top = sorted(cats, key=lambda c: rv.count(c) + cv.count(c), reverse=True)[:9]
        ra = [sum(x == c for x in rv) for c in top] + [sum(x not in top for x in rv)]
        ca = [sum(x == c for x in cv) for c in top] + [sum(x not in top for x in cv)]
        ap = np.maximum(np.asarray(ra) / len(rv), 1e-4)
        bp = np.maximum(np.asarray(ca) / len(cv), 1e-4)
        v = float(np.sum((bp - ap) * np.log(bp / ap)))
        features_out.append(
            {
                "feature": field,
                "psi": v,
                "threshold": 0.2,
                "drifted": v >= 0.2,
                "categories": top + ["other"],
                "reference_distribution": ra,
                "current_distribution": ca,
            }
        )
    report_id = f"drift-report-{uuid4().hex[:12]}"
    payload = {
        "reference_version": reference.version,
        "current_version": current.version,
        "status": "drift_detected"
        if any(x["drifted"] for x in features_out)
        else "no_significant_drift",
        "method": "Population Stability Index (PSI)",
        "interpretation": "Feature distribution change only; this does not establish concept drift or performance degradation.",
        "features": features_out,
        "threshold": 0.2,
    }
    _record(db, "drift_report", report_id, payload, user.username)
    log(db, user.username, "mlops.drift_detected", report_id, details={"status": payload["status"]})
    db.commit()
    return {"version": report_id, **payload}


@app.post("/api/mlops/retrain")
def mlops_retrain(
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(allow("Administrator", "ML Engineer")),
):
    dataset_version = body.get("dataset_version")
    dataset = db.query(DemoDataset).filter_by(version=dataset_version, kind="drift").first()
    versioned = db.get(DatasetVersion, dataset_version) if not dataset and dataset_version else None
    if not dataset:
        if not versioned:
            raise HTTPException(404, "Training dataset not found")
        if versioned.status != "ready":
            raise HTTPException(409, "Operational dataset must be ready before retraining")
        training_rows = _operational_training_rows(db, versioned.version)
        selected_version = versioned.version
    else:
        training_rows = dataset.events
        selected_version = dataset.version
    result = train_model(rows=training_rows, dataset_version=selected_version)
    result["dataset_version"] = selected_version
    row = ModelRun(
        version=result["version"],
        algorithm=result["algorithm"],
        dataset_version=selected_version,
        metrics=result["metrics"],
        artifact_path=result["artifact_path"],
    )
    db.add(row)
    run_id = None
    tracking_error = None
    try:
        run_id = track_training_run(result)
        row.mlflow_run_id = run_id
    except Exception as exc:
        tracking_error = str(exc)[:300]
        log(db, user.username, "mlflow.unavailable", result["version"], reason=tracking_error)
    _record(
        db,
        "retraining",
        result["version"],
        {
            "dataset_version": selected_version,
            "reason": str(body.get("reason", "detected data drift")),
            "mlflow_run_id": run_id,
            "tracking_error": tracking_error,
            "metrics": result["metrics"],
            "status": "completed",
        },
        user.username,
    )
    log(
        db,
        user.username,
        "model.candidate_trained",
        result["version"],
        details={"dataset_version": selected_version, "mlflow_run_id": run_id},
    )
    db.commit()
    return {
        "version": result["version"],
        "dataset_version": selected_version,
        "metrics": result["metrics"],
        "mlflow_run_id": run_id,
        "tracking_error": tracking_error,
        "status": "completed",
    }


def _evaluate(model, events, threshold=0.30):
    ordered = sorted(events, key=lambda e: e["event_time"])
    # Match train_model: validation rows may be used for fitting, but its final
    # chronological 15% test segment must stay untouched for both contestants.
    cut = int(len(ordered) * 0.85)
    holdout = ordered[cut:]
    X = model_input(model, features(ordered).iloc[cut:])
    y = np.asarray([int(e.get("fraud_label") or 0) for e in holdout])
    p = model["model"].predict_proba(X)[:, 1]
    pred = (p >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "pr_auc": float(average_precision_score(y, p)),
        "false_positive_rate": float(fp / max(fp + tn, 1)),
        "confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
        "threshold": threshold,
    }


def _operational_training_rows(db: Session, dataset_version: str):
    rows = []
    query = (
        db.query(Event).filter(Event.dataset_version == dataset_version)
        .order_by(Event.event_time).yield_per(10_000)
    )
    for event in query:
        rows.append({
            "event_id": event.event_id, "event_type": event.event_type,
            "event_time": event.event_time, "subscriber_id": event.subscriber_id,
            "source_token": event.source_token, "destination_token": event.destination_token,
            "sim_id": event.sim_id, "device_id": event.device_id,
            "network_token": event.network_token, "location_token": event.location_token,
            "latitude": event.latitude, "longitude": event.longitude,
            "duration_seconds": event.duration_seconds, "call_direction": event.call_direction,
            "call_status": event.call_status, "is_international": event.is_international,
            "is_roaming": event.is_roaming, "message_count": event.message_count,
            "auth_outcome": event.auth_outcome, "scenario_label": event.scenario_label,
            "fraud_label": event.fraud_label,
        })
    return rows


@app.post("/api/mlops/compare")
def mlops_compare(
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(allow("Administrator", "ML Engineer")),
):
    challenger = db.query(ModelRun).filter_by(version=body.get("challenger_version")).first()
    dataset = db.query(DemoDataset).filter_by(version=challenger.dataset_version).first() if challenger else None
    versioned = db.get(DatasetVersion, challenger.dataset_version) if challenger and not dataset else None
    if not challenger or not (dataset or versioned):
        raise HTTPException(404, "Candidate or its evaluation dataset is missing")
    if versioned and versioned.status != "ready":
        raise HTTPException(409, "Operational evaluation dataset is not ready")
    active_version = _mlops_state(db)
    champion_row = db.query(ModelRun).filter_by(version=active_version).first()
    if not champion_row:
        raise HTTPException(409, "Active champion metadata is missing")
    champion = load_model_run(champion_row)
    challenger_model = load_model_run(challenger)
    evaluation_events = dataset.events if dataset else _operational_training_rows(db, versioned.version)
    if len(evaluation_events) < 10:
        raise HTTPException(409, "Evaluation dataset has too few labeled events")
    champion_metrics = _evaluate(champion, evaluation_events)
    challenger_metrics = _evaluate(challenger_model, evaluation_events)
    passed = (
        challenger_metrics["pr_auc"] >= champion_metrics["pr_auc"] - 0.02
        and challenger_metrics["recall"] >= champion_metrics["recall"] - 0.03
        and challenger_metrics["false_positive_rate"]
        <= champion_metrics["false_positive_rate"] + 0.03
    )
    payload = {
        "champion_version": active_version,
        "challenger_version": challenger.version,
        "dataset_version": dataset.version if dataset else versioned.version,
        "champion": champion_metrics,
        "challenger": challenger_metrics,
        "gates": {
            "pr_auc_no_more_than_0.02_worse": challenger_metrics["pr_auc"]
            >= champion_metrics["pr_auc"] - 0.02,
            "recall_no_more_than_0.03_worse": challenger_metrics["recall"]
            >= champion_metrics["recall"] - 0.03,
            "fpr_no_more_than_0.03_worse": challenger_metrics["false_positive_rate"]
            <= champion_metrics["false_positive_rate"] + 0.03,
        },
        "passed": passed,
        "policy": "same untouched chronological 15% test holdout after 70/15/15 train/validation/test; threshold=0.30; PR-AUC, recall and false-positive gates",
    }
    comparison_id = f"comparison-{uuid4().hex[:10]}"
    _record(db, "comparison", comparison_id, payload, user.username)
    db.commit()
    return {"version": comparison_id, **payload}


@app.post("/api/mlops/decisions/{candidate_version}")
def mlops_decision(
    candidate_version: str,
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(allow("Administrator")),
):
    action_name = body.get("decision")
    candidate = db.query(ModelRun).filter_by(version=candidate_version).first()
    if action_name not in {"approve", "reject"} or not candidate:
        raise HTTPException(422, "A valid candidate and approve/reject decision are required")
    comparison = (
        db.query(MLOpsRecord).filter_by(kind="comparison").order_by(MLOpsRecord.id.desc()).first()
    )
    if not comparison or comparison.payload.get("challenger_version") != candidate_version:
        raise HTTPException(409, "Compare this challenger against the current champion first")
    if action_name == "approve" and not comparison.payload.get("passed"):
        raise HTTPException(409, "Promotion gates failed; the champion remains active")
    _record(
        db,
        "approved_model" if action_name == "approve" else "rejected_model",
        candidate_version,
        {
            "decision": action_name,
            "comparison": comparison.version,
            "metrics": comparison.payload,
            "approver": user.username,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        user.username,
    )
    if action_name == "approve":
        _record(
            db,
            "active_model",
            candidate_version,
            {"reason": "administrator-approved promotion"},
            user.username,
        )
        app.state.model = load_model_run(candidate)
        _stop_challenger_serving(db, user.username, "champion promotion")
    elif current_serving_config(db).get("challenger_version") == candidate_version:
        _stop_challenger_serving(db, user.username, "challenger rejected")
    log(
        db,
        user.username,
        "model.approved" if action_name == "approve" else "model.rejected",
        candidate_version,
        reason=body.get("reason"),
        details={"comparison": comparison.version},
    )
    db.commit()
    return {"decision": action_name, "active_model": _mlops_state(db), "version": candidate_version}


@app.post("/api/mlops/rollback")
def mlops_rollback(
    body: dict, db: Session = Depends(get_db), user: User = Depends(allow("Administrator"))
):
    version = body.get("version")
    approved = db.query(MLOpsRecord).filter_by(kind="approved_model", version=version).first()
    model_row = db.query(ModelRun).filter_by(version=version).first()
    if not approved or not model_row:
        raise HTTPException(404, "Rollback target must be an existing approved model")
    _record(
        db,
        "active_model",
        version,
        {"reason": str(body.get("reason", "administrator rollback"))},
        user.username,
    )
    restored_model = load_model_run(model_row)
    _stop_challenger_serving(db, user.username, "champion rollback")
    log(db, user.username, "model.rollback", version, reason=body.get("reason"))
    db.commit()
    app.state.model = restored_model
    return {"active_model": version, "rolled_back": True}


@app.post("/api/mlops/reset-demo")
def reset_mlops_demo(db: Session = Depends(get_db), user: User = Depends(allow("Administrator"))):
    db.query(DemoDataset).filter(DemoDataset.kind == "drift").delete(synchronize_session=False)
    db.query(MLOpsRecord).filter(
        MLOpsRecord.kind.in_(["drift_report", "comparison", "retraining", "rejected_model"])
    ).delete(synchronize_session=False)
    log(
        db,
        user.username,
        "mlops.demo_reset",
        "demo-only",
        details={"baseline_and_models_preserved": True},
    )
    db.commit()
    return {"reset": True, "baseline_preserved": True, "models_preserved": True}


@app.get("/api/audit")
def audit(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(allow("Administrator", "Auditor")),
):
    return [
        {
            "actor": a.actor,
            "action": a.action,
            "target": a.target,
            "reason": a.reason,
            "details": a.details,
            "created_at": a.created_at.isoformat(),
        }
        for a in db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    ]


@app.get("/api/entities/{subscriber_id}")
def entity(subscriber_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = (
        db.query(Event)
        .filter_by(subscriber_id=subscriber_id)
        .order_by(Event.event_time.desc())
        .limit(100)
        .all()
    )
    if not rows:
        raise HTTPException(404, "Subscriber not found")
    return {
        "subscriber_id": subscriber_id,
        "events": [event_dict(e) for e in rows],
        "predictions": [
            prediction_dict(p)
            for p in db.query(Prediction)
            .join(Event, Prediction.event_id == Event.event_id)
            .filter(Event.subscriber_id == subscriber_id)
            .all()
        ],
    }


@app.get("/api/graph")
def graph(
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    import networkx as nx

    network = nx.Graph()
    for event in db.query(Event).order_by(Event.event_time.desc()).limit(limit).all():
        subscriber = f"subscriber:{event.subscriber_id}"
        network.add_node(subscriber, kind="subscriber", token=event.subscriber_id)
        for value, kind in (
            (event.device_id, "device"),
            (event.network_token, "network"),
            (event.sim_id, "sim"),
        ):
            if value:
                entity_token = f"{kind}:{value}"
                network.add_node(entity_token, kind=kind, token=value)
                network.add_edge(
                    subscriber,
                    entity_token,
                    event_id=event.event_id,
                    event_time=event.event_time.isoformat(),
                )
    return {
        "nodes": [
            {"id": n, **attrs, "degree": network.degree[n]} for n, attrs in network.nodes(data=True)
        ],
        "edges": [{"source": a, "target": b, **attrs} for a, b, attrs in network.edges(data=True)],
    }
