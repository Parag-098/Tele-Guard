"""Correlate alert evidence and retain human adjudication separately from case status."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import blake2b
from statistics import median
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func, or_, select, text
from sqlalchemy.orm import Mapped, Session, aliased, mapped_column, relationship

from app.config import settings
from app.db import Base, get_db
from app.models import AuditLog, Event, Incident, ModelObservation, Note, Prediction, ResponseAction, User, now
from app.security import allow, current_user

router = APIRouter(prefix="/api")
reviewer = allow("Administrator", "Fraud Analyst", "Investigator")
case_operator = allow("Administrator", "Investigator")
analytics_reader = allow("Administrator", "Fraud Analyst", "Investigator", "ML Engineer", "Auditor")
OUTCOMES = Literal["confirmed_fraud", "legitimate", "false_positive", "inconclusive", "duplicate"]
RATIONALE = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=1000)]
LABELS = {"confirmed_fraud": 1, "legitimate": 0, "false_positive": 0}
OPEN_STATUSES = ("New", "Investigating", "Escalated")
SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class CasePrediction(Base):
    __tablename__ = "case_predictions"

    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    decision: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    incident: Mapped[Incident] = relationship()


class CaseMerge(Base):
    __tablename__ = "case_merges"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    actor: Mapped[str] = mapped_column(String(80))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversed_by: Mapped[str | None] = mapped_column(String(80))
    reversal_reason: Mapped[str | None] = mapped_column(Text)


class Adjudication(Base):
    __tablename__ = "adjudications"
    __table_args__ = (
        CheckConstraint(
            "(incident_id IS NULL) <> (prediction_id IS NULL)", name="ck_adjudication_scope"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str | None] = mapped_column(String(36), unique=True)
    incident_id: Mapped[int | None] = mapped_column(ForeignKey("incidents.id"), index=True)
    prediction_id: Mapped[int | None] = mapped_column(ForeignKey("predictions.id"), index=True)
    correction_of: Mapped[int | None] = mapped_column(ForeignKey("adjudications.id"))
    outcome: Mapped[str] = mapped_column(String(30))
    reviewer: Mapped[str] = mapped_column(String(80))
    reason: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(40), default="analyst_review")
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


@dataclass(frozen=True)
class CasePolicy:
    max_age_minutes: int = 120
    max_events: int = 40
    cross_entity_min_risk: float = 0.60


policy = CasePolicy(
    max_age_minutes=settings.case_max_age_minutes,
    max_events=settings.case_max_events,
    cross_entity_min_risk=settings.case_cross_entity_min_risk,
)


def _utc(timestamp: datetime) -> datetime:
    return timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)


def _correlation_reason(anchor, event, risk: float) -> str | None:
    age = _utc(event.event_time) - _utc(anchor.event_time)
    if (
        anchor.dataset_version != event.dataset_version
        or age < timedelta(0)
        or age > timedelta(minutes=policy.max_age_minutes)
    ):
        return None
    if anchor.subscriber_id == event.subscriber_id:
        return "same_subscriber"
    if (
        risk >= policy.cross_entity_min_risk
        and event.device_id
        and event.network_token
        and event.device_id == anchor.device_id
        and event.network_token == anchor.network_token
    ):
        return "shared_device_and_network"
    return None


@dataclass
class _Case:
    anchor: Event
    detail: Incident
    count: int


class _CaseIndex:
    def __init__(self):
        self.by_subscriber = defaultdict(list)
        self.by_device_and_network = defaultdict(list)

    def add(self, case: _Case) -> None:
        anchor = case.anchor
        self.by_subscriber[anchor.subscriber_id].append(case)
        if anchor.device_id and anchor.network_token:
            self.by_device_and_network[anchor.device_id, anchor.network_token].append(case)

    def match(self, event: Event, risk: float) -> tuple[_Case | None, str]:
        matching = (
            self.by_subscriber.get(event.subscriber_id, [])
            + self.by_device_and_network.get((event.device_id, event.network_token), [])
        )
        candidates = []
        for candidate in matching:
            if candidate.count >= policy.max_events:
                continue
            reason = _correlation_reason(candidate.anchor, event, risk)
            if reason:
                candidates.append((candidate, reason))
        return max(
            candidates,
            key=lambda match: (
                match[1] == "same_subscriber",
                _utc(match[0].anchor.event_time),
                match[0].anchor.event_id,
            ),
            default=(None, "first_alert"),
        )


def _audit(db: Session, actor: str, action: str, target: str, reason: str, **details):
    db.add(AuditLog(actor=actor, action=action, target=target, reason=reason, details=details))


def _serialize_case_writes(db: Session) -> None:
    # Scoring has already completed when this transaction lock is taken. It prevents
    # two workers from creating different first cases for the same alert group.
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(720392116)"))


def visible_case_filter():
    """Keep consolidated CASE records available by ID while hiding them from the queue."""
    return Incident.id.not_in(select(CaseMerge.source_id).where(CaseMerge.reversed_at.is_(None)))


def attach_prediction(db: Session, event: Event, prediction: Prediction, actor: str) -> None:
    attach_predictions(db, [(event, prediction)], actor)


def attach_predictions(db: Session, rows, actor: str) -> None:
    """Pair scored predictions with one bounded case without changing historical incidents."""
    alerts = sorted(
        ((event, prediction) for event, prediction in rows
         if prediction.risk_score >= settings.incident_risk_threshold),
        key=lambda pair: (_utc(pair[0].event_time), pair[0].event_id),
    )
    if not alerts:
        return
    _serialize_case_writes(db)
    db.flush()
    ids = [prediction.id for _, prediction in alerts]
    attached = set(db.scalars(select(CasePrediction.prediction_id).where(
        CasePrediction.prediction_id.in_(ids)
    )))
    attached.update(db.scalars(select(Incident.prediction_id).where(Incident.prediction_id.in_(ids))))
    alerts = [(event, prediction) for event, prediction in alerts if prediction.id not in attached]
    if not alerts:
        return

    start = _utc(alerts[0][0].event_time) - timedelta(minutes=policy.max_age_minutes)
    end = _utc(alerts[-1][0].event_time)
    subscribers = {event.subscriber_id for event, _ in alerts}
    devices = {event.device_id for event, _ in alerts if event.device_id}
    networks = {event.network_token for event, _ in alerts if event.network_token}
    anchors = db.execute(
        select(Incident, Event)
        .join(Prediction, Prediction.id == Incident.prediction_id)
        .join(Event, Event.event_id == Prediction.event_id)
        .where(
            Incident.status.in_(OPEN_STATUSES),
            visible_case_filter(),
            Event.event_time.between(start, end),
            or_(
                Event.subscriber_id.in_(subscribers),
                Event.device_id.in_(devices) & Event.network_token.in_(networks),
            ),
        )
        .order_by(Event.event_time.desc(), Event.event_id.desc(), Incident.id.desc())
        .limit(10000)
    ).all()
    anchor_ids = {incident.id for incident, _ in anchors}
    merges = db.execute(select(CaseMerge.source_id, CaseMerge.target_id).where(
        CaseMerge.target_id.in_(anchor_ids),
        CaseMerge.reversed_at.is_(None),
    )).all() if anchor_ids else []
    related_ids = anchor_ids | {source_id for source_id, _ in merges}
    counts = dict(db.execute(
        select(CasePrediction.incident_id, func.count())
        .where(CasePrediction.incident_id.in_(related_ids))
        .group_by(CasePrediction.incident_id)
    ).all()) if related_ids else {}
    unmapped_anchors = db.scalars(
        select(Incident.id).where(
            Incident.id.in_(related_ids),
            ~select(CasePrediction.prediction_id)
            .where(CasePrediction.prediction_id == Incident.prediction_id)
            .exists(),
        )
    ) if related_ids else []
    for incident_id in unmapped_anchors:
        counts[incident_id] = counts.get(incident_id, 0) + 1
    for source_id, target_id in merges:
        counts[target_id] = counts.get(target_id, 1) + counts.get(source_id, 1)
    index = _CaseIndex()
    for incident, anchor in anchors:
        index.add(_Case(anchor, incident, counts.get(incident.id, 1)))

    for event, prediction in alerts:
        if prediction.id in attached:
            continue
        attached.add(prediction.id)
        candidate, decision = index.match(event, prediction.risk_score)
        if candidate is None:
            incident = Incident(
                prediction_id=prediction.id,
                subscriber_id=event.subscriber_id,
                title=f"Elevated synthetic risk — {event.event_type}",
                severity=prediction.risk_band,
                status="New",
            )
            candidate = _Case(event, incident, 0)
            index.add(candidate)
        if SEVERITY_ORDER.get(prediction.risk_band.lower(), -1) > SEVERITY_ORDER.get(
            candidate.detail.severity.lower(), -1
        ):
            candidate.detail.severity = prediction.risk_band
        candidate.count += 1
        db.add(CasePrediction(
            prediction_id=prediction.id, incident=candidate.detail, decision=decision, actor=actor
        ))


def _get_case(db: Session, incident_id: int) -> Incident:
    item = db.get(Incident, incident_id)
    if item is None:
        raise HTTPException(404, "Investigation not found")
    return item


def _active_merge(db: Session, source_id: int) -> CaseMerge | None:
    return db.scalar(select(CaseMerge).where(
        CaseMerge.source_id == source_id, CaseMerge.reversed_at.is_(None)
    ))


def _prediction_case(db: Session, prediction_id: int) -> Incident | None:
    return db.scalar(select(Incident).where(
        or_(
            Incident.prediction_id == prediction_id,
            Incident.id.in_(select(CasePrediction.incident_id).where(
                CasePrediction.prediction_id == prediction_id
            )),
        )
    ).order_by(Incident.id).limit(1))


def _latest_review(db: Session, target, target_id: int, cutoff: datetime | None = None):
    stmt = select(Adjudication).where(target == target_id)
    if cutoff:
        stmt = stmt.where(Adjudication.reviewed_at <= cutoff)
    return db.scalar(stmt.order_by(Adjudication.id.desc()).limit(1))


def _review_dict(review: Adjudication) -> dict:
    return {
        "id": review.id, "prediction_id": review.prediction_id, "incident_id": review.incident_id,
        "outcome": review.outcome, "source": review.source, "reviewer": review.reviewer,
        "reason": review.reason, "reviewed_at": _utc(review.reviewed_at).isoformat(),
        "correction_of": review.correction_of,
    }


def _review_conflicts(db: Session, prediction_id: int, outcome: str, cutoff=None) -> bool:
    incident = _prediction_case(db, prediction_id)
    case_review = _latest_review(db, Adjudication.incident_id, incident.id, cutoff) if incident else None
    return bool(
        case_review and case_review.outcome in LABELS and outcome in LABELS
        and LABELS[case_review.outcome] != LABELS[outcome]
    )


def approved_labels(db: Session, cutoff: datetime) -> dict[str, int]:
    """Freeze explicit event review as of the cutoff, excluding conflicting case evidence."""
    newest = (
        select(func.max(Adjudication.id))
        .where(Adjudication.prediction_id.is_not(None), Adjudication.reviewed_at <= cutoff,
               Adjudication.source == "analyst_review", Adjudication.reviewer != "",
               func.length(Adjudication.reason) >= 5)
        .group_by(Adjudication.prediction_id)
    )
    # A linked event is evaluated against its own originating case. Merging cases for
    # triage changes what is displayed in a timeline, not the scope of earlier reviews.
    original_case = (
        select(func.min(Incident.id)).where(Incident.prediction_id == Prediction.id)
        .correlate(Prediction).scalar_subquery()
    )
    case_reviews = (
        select(Adjudication.incident_id, func.max(Adjudication.id).label("latest_id"))
        .where(Adjudication.incident_id.is_not(None), Adjudication.reviewed_at <= cutoff)
        .group_by(Adjudication.incident_id).subquery()
    )
    case_review = aliased(Adjudication)
    rows = db.execute(
        select(Adjudication.outcome, Prediction.event_id, case_review.outcome)
        .join(Prediction, Prediction.id == Adjudication.prediction_id)
        .outerjoin(CasePrediction, CasePrediction.prediction_id == Prediction.id)
        .outerjoin(
            case_reviews,
            case_reviews.c.incident_id == func.coalesce(CasePrediction.incident_id, original_case),
        )
        .outerjoin(case_review, case_review.id == case_reviews.c.latest_id)
        .where(Adjudication.id.in_(newest), Adjudication.outcome.in_(LABELS))
    ).all()
    return {
        event_id: LABELS[outcome]
        for outcome, event_id, case_outcome in rows
        if case_outcome not in LABELS or LABELS[case_outcome] == LABELS[outcome]
    }


class ReviewRequest(BaseModel):
    outcome: OUTCOMES
    reason: RATIONALE
    correction_of: int | None = Field(default=None, ge=1)
    request_id: UUID | None = None


class LegacyLabelRequest(BaseModel):
    """Backward-compatible binary label shape with governed review provenance."""
    label: Literal[0, 1]
    reason: RATIONALE
    correction_of: int | None = Field(default=None, ge=1)
    request_id: UUID | None = None


def _submit_review(db, body, user, *, prediction=None, incident=None) -> Adjudication:
    _serialize_case_writes(db)
    if prediction:
        db.refresh(prediction, with_for_update=True)
    prediction_id = prediction.id if prediction else None
    incident_id = incident.id if incident else None
    request_id = str(body.request_id) if body.request_id else None
    if request_id:
        existing = db.scalar(select(Adjudication).where(Adjudication.request_id == request_id))
        if existing:
            if (
                existing.prediction_id, existing.incident_id, existing.outcome,
                existing.reviewer, existing.reason, existing.correction_of
            ) != (prediction_id, incident_id, body.outcome, user.username, body.reason, body.correction_of):
                raise HTTPException(409, "Request ID was already used for a different adjudication")
            return existing

    previous = _latest_review(db, Adjudication.prediction_id, prediction_id) if prediction else (
        _latest_review(db, Adjudication.incident_id, incident_id)
    )
    if body.correction_of != (previous.id if previous else None):
        raise HTTPException(409, "A correction must reference the latest adjudication")
    if previous and previous.reviewer != user.username and user.role != "Administrator":
        raise HTTPException(403, "Only the original reviewer or an administrator can correct this review")
    if body.outcome in LABELS and prediction and prediction.label_source not in (None, "analyst_review"):
        if prediction.ground_truth_label != LABELS[body.outcome]:
            raise HTTPException(409, "The reviewed outcome conflicts with a previously released label")
    entry = Adjudication(
        request_id=request_id, prediction_id=prediction_id, incident_id=incident_id,
        outcome=body.outcome, reviewer=user.username, reason=body.reason,
        correction_of=body.correction_of, reviewed_at=now(),
    )
    db.add(entry)
    db.flush()
    target = prediction.event_id if prediction else str(incident_id)
    _audit(db, user.username, "prediction.adjudicated" if prediction else "incident.adjudicated",
           target, body.reason, adjudication_id=entry.id, outcome=body.outcome)
    if prediction:
        _project_review(db, prediction, entry)
    else:
        affected = db.scalars(select(Prediction).where(
            or_(Prediction.id == incident.prediction_id,
                Prediction.id.in_(select(CasePrediction.prediction_id).where(
                    CasePrediction.incident_id == incident.id
                ))),
            Prediction.id.in_(select(Adjudication.prediction_id).where(
                Adjudication.prediction_id.is_not(None)
            )),
        ).order_by(Prediction.id).with_for_update())
        for item in affected:
            _project_review(db, item, _latest_review(db, Adjudication.prediction_id, item.id))
    db.commit()
    return entry


def _project_review(db: Session, prediction: Prediction, entry: Adjudication) -> None:
    if prediction.label_source not in (None, "analyst_review"):
        return
    label = LABELS.get(entry.outcome)
    if _review_conflicts(db, prediction.id, entry.outcome):
        label = None
    if label is not None or prediction.label_source == "analyst_review":
        prediction.ground_truth_label = label
        prediction.label_source = "analyst_review" if label is not None else None
        prediction.label_received_at = entry.reviewed_at if label is not None else None
        db.query(ModelObservation).filter_by(prediction_id=prediction.id).update({
            "outcome_label": label, "evaluated_at": prediction.label_received_at,
        })


@router.post("/predictions/{event_id}/adjudications", status_code=201)
def adjudicate_prediction(event_id: str, body: ReviewRequest, db: Session = Depends(get_db),
                          user: User = Depends(reviewer)):
    prediction = db.scalar(select(Prediction).where(Prediction.event_id == event_id))
    if prediction is None:
        raise HTTPException(404, "Prediction not found")
    return _review_dict(_submit_review(db, body, user, prediction=prediction))


@router.post("/incidents/{incident_id}/adjudications", status_code=201)
def adjudicate_case(incident_id: int, body: ReviewRequest, db: Session = Depends(get_db),
                    user: User = Depends(reviewer)):
    return _review_dict(_submit_review(db, body, user, incident=_get_case(db, incident_id)))


@router.get("/predictions/{event_id}/adjudications")
def prediction_adjudications(event_id: str, db: Session = Depends(get_db),
                             _user: User = Depends(current_user)):
    rows = db.scalars(
        select(Adjudication).join(Prediction, Prediction.id == Adjudication.prediction_id)
        .where(Prediction.event_id == event_id).order_by(Adjudication.id.desc()).limit(100)
    )
    return [_review_dict(row) for row in rows]


class CaseChange(BaseModel):
    reason: RATIONALE


class MergeRequest(CaseChange):
    source_id: int = Field(ge=1)


def _case_anchor(db: Session, incident: Incident) -> tuple[Event, Prediction]:
    return db.execute(select(Event, Prediction).join(
        Prediction, Prediction.event_id == Event.event_id
    ).where(Prediction.id == incident.prediction_id)).one()


@router.post("/incidents/{incident_id}/merge", status_code=201)
def merge_case(incident_id: int, body: MergeRequest, db: Session = Depends(get_db),
               user: User = Depends(case_operator)):
    _serialize_case_writes(db)
    target, source = _get_case(db, incident_id), _get_case(db, body.source_id)
    if target.id == source.id:
        raise HTTPException(422, "Choose two different investigations")
    current = _active_merge(db, source.id)
    if current and current.target_id == target.id and current.actor == user.username and current.reason == body.reason:
        return {"merge_id": current.id, "source_id": source.id, "target_id": target.id}
    if current or _active_merge(db, target.id) or db.scalar(
        select(CaseMerge.id).where(CaseMerge.target_id == source.id, CaseMerge.reversed_at.is_(None)).limit(1)
    ):
        raise HTTPException(409, "One of these cases is already involved in a consolidation")
    first, second = _case_anchor(db, target), _case_anchor(db, source)
    if _utc(second[0].event_time) < _utc(first[0].event_time):
        first, second = second, first
    evidence = _correlation_reason(first[0], second[0], second[1].risk_score)
    if not evidence:
        raise HTTPException(409, "The case anchors lack corroborated evidence within the case window")
    historical_sources = list(db.scalars(select(CaseMerge.source_id).where(
        CaseMerge.target_id == target.id, CaseMerge.reversed_at.is_(None)
    )))
    case_ids = [target.id, source.id, *historical_sources]
    count = db.scalar(select(func.count()).select_from(select(Incident.prediction_id).where(
        Incident.id.in_(case_ids)
    ).union(select(CasePrediction.prediction_id).where(
        CasePrediction.incident_id.in_(case_ids)
    )).subquery()))
    if count > policy.max_events:
        raise HTTPException(409, "Consolidation would exceed the configured case size")
    entry = CaseMerge(source_id=source.id, target_id=target.id, actor=user.username, reason=body.reason)
    db.add(entry)
    _audit(db, user.username, "incident.merged", str(target.id), body.reason,
           source_id=source.id, evidence=evidence)
    db.commit()
    return {"merge_id": entry.id, "source_id": source.id, "target_id": target.id}


@router.post("/incidents/{incident_id}/unmerge")
def unmerge_case(incident_id: int, body: CaseChange, db: Session = Depends(get_db),
                 user: User = Depends(case_operator)):
    _serialize_case_writes(db)
    entry = _active_merge(db, incident_id)
    if not entry:
        raise HTTPException(404, "No active consolidation for this source case")
    entry.reversed_at, entry.reversed_by, entry.reversal_reason = now(), user.username, body.reason
    _audit(db, user.username, "incident.merge_reversed", str(entry.target_id), body.reason,
           source_id=entry.source_id, merge_id=entry.id)
    db.commit()
    return {"merge_id": entry.id, "source_id": entry.source_id, "target_id": entry.target_id}


@router.post("/incidents/{incident_id}/reopen")
def reopen_case(incident_id: int, body: CaseChange, db: Session = Depends(get_db),
                user: User = Depends(case_operator)):
    _serialize_case_writes(db)
    item = _get_case(db, incident_id)
    if item.status in OPEN_STATUSES or _active_merge(db, item.id):
        raise HTTPException(409, "Only a closed, independent investigation can be reopened")
    _audit(db, user.username, "incident.reopened", str(item.id), body.reason, previous={
        "status": item.status, "outcome": item.resolution_outcome, "reason": item.resolution_reason,
        "resolved_by": item.resolved_by,
        "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
    })
    item.status = "Investigating"
    item.resolution_outcome = item.resolution_reason = item.resolved_by = item.resolved_at = None
    db.commit()
    return {"incident_id": item.id, "status": item.status}


@router.get("/incidents/{incident_id}/timeline")
def case_timeline(incident_id: int, db: Session = Depends(get_db),
                  _user: User = Depends(current_user)):
    item = _get_case(db, incident_id)
    sources = list(db.scalars(select(CaseMerge).where(
        or_(CaseMerge.source_id == item.id, CaseMerge.target_id == item.id)
    ).order_by(CaseMerge.id.desc()).limit(100)))
    incident_ids = {item.id}
    incident_ids.update(m.source_id for m in sources if m.target_id == item.id and not m.reversed_at)
    case_link = aliased(CasePrediction)
    rows = db.execute(
        select(Prediction, Event, case_link.decision)
        .join(Event, Event.event_id == Prediction.event_id)
        .outerjoin(case_link, case_link.prediction_id == Prediction.id)
        .where(or_(
            case_link.incident_id.in_(incident_ids),
            Prediction.id.in_(select(Incident.prediction_id).where(Incident.id.in_(incident_ids))),
        ))
        .order_by(Event.event_time, Event.event_id)
        .limit(policy.max_events + 1)
    ).all()
    visible_rows = rows[:policy.max_events]
    return {
        "incident_id": item.id,
        "events": [{
            "event_id": event.event_id, "event_time": _utc(event.event_time).isoformat(),
            "event_type": event.event_type, "subscriber_id": event.subscriber_id,
            "device_id": event.device_id, "network_token": event.network_token,
            "risk_score": prediction.risk_score, "risk_band": prediction.risk_band,
            "model_version": prediction.model_version, "decision": decision or "original_alert",
        } for prediction, event, decision in visible_rows],
        "truncated": len(rows) > policy.max_events,
        "adjudications": [_review_dict(row) for row in db.scalars(select(Adjudication).where(
            Adjudication.incident_id.in_(incident_ids)
        ).order_by(Adjudication.id.desc()).limit(100))],
        "notes": [{
            "id": note.id, "incident_id": note.incident_id, "author": note.author, "body": note.body,
            "created_at": _utc(note.created_at).isoformat(),
        } for note in db.scalars(select(Note).where(Note.incident_id.in_(incident_ids))
                                .order_by(Note.id.desc()).limit(100))],
        "actions": [{
            "id": action.id, "incident_id": action.incident_id, "actor": action.actor,
            "action": action.action, "reason": action.reason, "reverses_id": action.reverses_id,
            "created_at": _utc(action.created_at).isoformat(),
        } for action in db.scalars(select(ResponseAction).where(
            ResponseAction.incident_id.in_(incident_ids)
        ).order_by(ResponseAction.id.desc()).limit(100))],
        "consolidations": [{
            "id": entry.id, "source_id": entry.source_id, "target_id": entry.target_id,
            "reason": entry.reason, "actor": entry.actor, "active": entry.reversed_at is None,
            "reversed_by": entry.reversed_by, "reversal_reason": entry.reversal_reason,
        } for entry in sources],
    }


@router.get("/review/queue")
def review_queue(limit: int = Query(20, ge=2, le=100), seed: int = 2026,
                 db: Session = Depends(get_db), _user: User = Depends(reviewer)):
    exclusions = select(Adjudication.prediction_id).where(Adjudication.prediction_id.is_not(None))
    rows = list(db.scalars(select(Prediction).where(
        Prediction.ground_truth_label.is_(None),
        Prediction.id.not_in(exclusions),
    ).order_by(Prediction.id.desc()).limit(2000)))
    low_risk = sorted(
        (row for row in rows if row.risk_score < settings.incident_risk_threshold),
        key=lambda row: blake2b(f"{seed}:{row.event_id}".encode(), digest_size=16).digest(),
    )
    selected_low_risk = low_risk[:limit // 2]
    selected_ids = {row.id for row in selected_low_risk}
    uncertainty = sorted(
        (row for row in rows if row.id not in selected_ids),
        key=lambda row: (abs(settings.incident_risk_threshold - row.risk_score), row.event_id),
    )
    return {
        "seed": seed, "population": len(rows), "eligible_low_risk": len(low_risk),
        "events": [
            {
                "event_id": row.event_id, "risk_score": row.risk_score,
                "sampling": "random_low_risk" if row.id in selected_ids else "near_alert_threshold",
            }
            for row in selected_low_risk + uncertainty[:limit - len(selected_low_risk)]
        ],
    }


def _replay_label(event: Event, prediction: Prediction) -> int | None:
    return prediction.ground_truth_label if prediction.ground_truth_label is not None else event.fraud_label


def _episode_index(rows):
    episode_by_event, episodes, latest = {}, {}, {}
    for event, prediction in rows:
        if _replay_label(event, prediction) != 1:
            continue
        family = event.scenario_label or "adjudicated"
        key = event.dataset_version, event.subscriber_id, family
        time = _utc(event.event_time)
        prior = latest.get(key)
        episode = prior[0] if prior and time - prior[1] <= timedelta(
            minutes=policy.max_age_minutes
        ) else event.event_id
        latest[key] = episode, time
        episode_by_event[event.event_id] = episode
        episodes.setdefault(episode, (family, time))
    return episode_by_event, episodes


def _replay_metrics(rows, cases, budget, episode_by_event, episodes):
    alerted = {}
    false_positives = unknown = false_merges = 0
    for linked in cases:
        ids, fully_labeled = set(), True
        for event, prediction in linked:
            episode = episode_by_event.get(event.event_id)
            if episode:
                ids.add(episode)
                time = _utc(event.event_time)
                alerted[episode] = min(time, alerted.get(episode, time))
            elif _replay_label(event, prediction) is None:
                fully_labeled = False
        false_merges += len(ids) > 1
        false_positives += not ids and fully_labeled
        unknown += not ids and not fully_labeled
    ranked = sorted(cases, key=lambda linked: (-max(p.risk_score for _, p in linked), linked[0][0].event_id))
    reviewed = ranked[:budget]
    reviewed_episodes = {
        episode_by_event[event.event_id]
        for linked in reviewed for event, _ in linked
        if event.event_id in episode_by_event
    }
    confirmed = sum(
        any(event.event_id in episode_by_event for event, _ in linked) for linked in reviewed
    )
    labeled_reviews = sum(
        any(event.event_id in episode_by_event for event, _ in linked)
        or all(_replay_label(event, prediction) is not None for event, prediction in linked)
        for linked in reviewed
    )
    by_family = {}
    for episode, (family, _) in episodes.items():
        totals = by_family.setdefault(family, {"episodes": 0, "detected": 0, "at_budget": 0})
        totals["episodes"] += 1
        totals["detected"] += episode in alerted
        totals["at_budget"] += episode in reviewed_episodes
    for totals in by_family.values():
        totals["recall"] = totals["detected"] / totals["episodes"]
    elapsed = [
        (observed_at - episodes[episode][1]).total_seconds()
        for episode, observed_at in alerted.items()
    ]
    return {
        "investigations": len(cases), "cases_per_1000_events": 1000 * len(cases) / max(len(rows), 1),
        "false_positive_cases": false_positives, "unlabeled_cases": unknown,
        "cases_spanning_multiple_episodes": false_merges,
        "fraud_episodes_detected": len(alerted), "fraud_episodes_total": len(episodes),
        "fraud_episodes_missed": len(episodes) - len(alerted),
        "episode_recall": len(alerted) / len(episodes) if episodes else None,
        "by_fraud_family": by_family, "review_budget": budget, "reviewed_cases": len(reviewed),
        "labeled_reviewed_cases": labeled_reviews,
        "precision_at_budget": confirmed / labeled_reviews if labeled_reviews else None,
        "fraud_episodes_at_budget": len(reviewed_episodes),
        "median_seconds_to_first_alert": median(elapsed) if elapsed else None,
    }


def replay_impact(rows, budget: int) -> dict:
    rows = sorted(rows, key=lambda row: (_utc(row[0].event_time), row[0].event_id))
    episode_by_event, episodes = _episode_index(rows)
    baseline, correlated, index = [], {}, _CaseIndex()
    for event, prediction in rows:
        if prediction.risk_score < settings.incident_risk_threshold:
            continue
        baseline.append([(event, prediction)])
        candidate, _ = index.match(event, prediction.risk_score)
        if not candidate:
            candidate = _Case(event, Incident(), 0)
            index.add(candidate)
        candidate.count += 1
        correlated.setdefault(candidate.anchor.event_id, []).append((event, prediction))
    return {
        "episode_definition": (
            "Dataset, subscriber, and fraud family; more than "
            f"{policy.max_age_minutes} minutes of silence starts a new episode"
        ),
        "review_definition": "Cases ranked by maximum risk; precision covers reviewed cases with known outcomes",
        "event_count": len(rows), "alerts_evaluated": len(baseline),
        "duplicate_alert_reduction": 1 - len(correlated) / len(baseline) if baseline else None,
        "one_alert_per_event": _replay_metrics(rows, baseline, budget, episode_by_event, episodes),
        "correlated": _replay_metrics(rows, list(correlated.values()), budget, episode_by_event, episodes),
    }


@router.get("/analytics/impact")
def impact_analytics(
    dataset_version: str | None = Query(None, max_length=120),
    sample_limit: int = Query(5000, ge=1, le=10000),
    review_budget: int = Query(100, ge=1, le=10000),
    db: Session = Depends(get_db),
    _user: User = Depends(analytics_reader),
):
    query = select(Event, Prediction).join(Prediction, Prediction.event_id == Event.event_id)
    resolved = select(Incident.created_at, Incident.resolved_at).where(Incident.resolved_at.is_not(None))
    if dataset_version:
        query = query.where(Event.dataset_version == dataset_version)
        resolved = resolved.join(Prediction, Prediction.id == Incident.prediction_id).join(
            Event, Event.event_id == Prediction.event_id
        ).where(Event.dataset_version == dataset_version)
    rows = db.execute(query.order_by(Event.event_time.desc(), Event.event_id.desc())
                      .limit(sample_limit + 1)).all()
    durations = [
        (_utc(resolved_at) - _utc(created_at)).total_seconds()
        for created_at, resolved_at in db.execute(resolved.order_by(Incident.resolved_at.desc())
                                                .limit(sample_limit))
    ]
    return {
        **replay_impact(rows[:sample_limit], review_budget),
        "dataset_version": dataset_version, "sample_truncated": len(rows) > sample_limit,
        "live_resolution": {
            "case_count": len(durations), "median_seconds": median(durations) if durations else None,
        },
        "simulation_only": True,
    }
