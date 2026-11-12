from datetime import datetime, timezone
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator


class EventIn(BaseModel):
    event_id: str = Field(min_length=4, max_length=64)
    event_type: str
    event_time: datetime
    subscriber_id: str = Field(min_length=3, max_length=64)
    source_token: str | None = None
    destination_token: str | None = None
    sim_id: str | None = None
    device_id: str | None = None
    network_token: str | None = None
    location_token: str | None = None
    duration_seconds: int | None = Field(default=None, ge=0, le=86400)
    scenario_label: str | None = None
    fraud_label: int | None = Field(default=None, ge=0, le=1)
    contract_version: str = "event-v1"

    @field_validator("event_type")
    @classmethod
    def valid_event_type(cls, v):
        allowed = {
            "CALL",
            "SMS",
            "SIM_CHANGE",
            "DEVICE_CHANGE",
            "ACCOUNT_ACTIVITY",
            "NETWORK_ACTIVITY",
            "LOCATION",
        }
        if v not in allowed:
            raise ValueError("unsupported event_type")
        return v

    @field_validator("event_time")
    @classmethod
    def timezone_aware_utc(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("event_time must include a timezone offset")
        return value.astimezone(timezone.utc)

    @field_validator(
        "subscriber_id",
        "source_token",
        "destination_token",
        "sim_id",
        "device_id",
        "network_token",
        "location_token",
    )
    @classmethod
    def synthetic_token_only(cls, value):
        if value is not None and not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]{2,63}", value):
            raise ValueError(
                "identifiers must be synthetic tokens, not phone numbers or raw identifiers"
            )
        return value

    model_config = ConfigDict(extra="forbid")


class LoginIn(BaseModel):
    username: str
    password: str


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=3000)


class IncidentUpdate(BaseModel):
    status: str | None = None
    assigned_to: str | None = None
    reason: str = Field(min_length=3, max_length=500)


class ActionIn(BaseModel):
    action: str
    reason: str = Field(min_length=3, max_length=500)
