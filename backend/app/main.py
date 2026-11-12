from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, or_
from sqlalchemy.orm import Session
from app.config import settings
from app.db import Base, engine, get_db, SessionLocal
from app.models import User, Event, Prediction, Incident, AuditLog, Note, ModelRun, ResponseAction
from app.schemas import EventIn, LoginIn, NoteIn, IncidentUpdate, ActionIn
from app.security import allow, current_user, hash_password, verify_password, make_token
from app.ml import load_model, score, train_model, track_training_run, FEATURE_VERSION
from app.synthetic import generate_events


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    app.state.model = load_model()
    with SessionLocal() as db:
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
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        "duration_seconds": e.duration_seconds,
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
        "created_at": p.created_at.isoformat(),
    }


def score_event(db, event, user, model):
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
    result = score(event_dict(event), model, context)
    p = Prediction(
        event_id=event.event_id,
        model_version=model.get("version", settings.model_version),
        feature_version=FEATURE_VERSION,
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


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok", "database": "connected", "contract_version": "event-v1"}


@app.post("/api/auth/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(username=data.username, active=True).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Invalid username or password")
    log(db, user.username, "auth.login", user.username)
    db.commit()
    return {
        "access_token": make_token(user),
        "token_type": "bearer",
        "user": {"username": user.username, "role": user.role},
    }


@app.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return {"username": user.username, "role": user.role}


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


@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return {
        "events": db.query(Event).count(),
        "incidents": db.query(Incident).count(),
        "high_risk": db.query(Prediction).filter(Prediction.risk_score >= 0.6).count(),
        "avg_risk": db.query(func.avg(Prediction.risk_score)).scalar() or 0,
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
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    q = db.query(Event)
    if subscriber_id:
        q = q.filter_by(subscriber_id=subscriber_id)
    rows = q.order_by(Event.event_time.desc()).offset(offset).limit(limit).all()
    return [
        {
            **event_dict(e),
            "prediction": prediction_dict(
                db.query(Prediction).filter_by(event_id=e.event_id).first()
            )
            if db.query(Prediction).filter_by(event_id=e.event_id).first()
            else None,
        }
        for e in rows
    ]


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
    status: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    q = db.query(Incident)
    if status:
        q = q.filter_by(status=status)
    return [
        {
            "id": i.id,
            "subscriber_id": i.subscriber_id,
            "title": i.title,
            "status": i.status,
            "severity": i.severity,
            "assigned_to": i.assigned_to,
            "created_at": i.created_at.isoformat(),
            "prediction": prediction_dict(db.get(Prediction, i.prediction_id)),
            "notes": [
                {"author": n.author, "body": n.body, "created_at": n.created_at.isoformat()}
                for n in db.query(Note).filter_by(incident_id=i.id).all()
            ],
        }
        for i in q.order_by(Incident.created_at.desc()).limit(200).all()
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
    old = i.status
    if data.status:
        i.status = data.status
    if data.assigned_to is not None:
        i.assigned_to = data.assigned_to
    log(
        db,
        user.username,
        "incident.updated",
        str(i.id),
        data.reason,
        {"from": old, "to": i.status, "assigned_to": i.assigned_to},
    )
    db.commit()
    return {"id": i.id, "status": i.status, "assigned_to": i.assigned_to}


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
            dataset_version="scenario-v1-seed-2026",
            metrics=result["metrics"],
            artifact_path=result["artifact_path"],
        )
        db.add(row)
    app.state.model = load_model()
    try:
        track_training_run(result)
    except Exception as exc:
        log(db, user.username, "mlflow.unavailable", result["version"], reason=str(exc)[:500])
    log(db, user.username, "model.trained", row.version, details=result["metrics"])
    db.commit()
    return {
        "version": row.version,
        "metrics": row.metrics,
        "note": result["metrics"]["evaluation_note"],
    }


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
