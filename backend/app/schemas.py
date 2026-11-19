from datetime import datetime, timezone
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    duration_seconds: int | None = Field(default=None, ge=0, le=86400)
    call_direction: str | None = None
    call_status: str | None = None
    is_international: bool | None = None
    is_roaming: bool | None = None
    message_count: int | None = Field(default=None, ge=0, le=100000)
    auth_outcome: str | None = None
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
            "OTP_REQUEST",
            "AUTHENTICATION",
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

    @model_validator(mode="after")
    def coordinate_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be supplied together")
        return self

    @model_validator(mode="after")
    def telecom_metadata(self):
        if self.call_direction not in {None, "incoming", "outgoing"}:
            raise ValueError("call_direction must be incoming or outgoing")
        if self.call_status not in {None, "answered", "missed", "failed"}:
            raise ValueError("call_status must be answered, missed or failed")
        if self.auth_outcome not in {None, "success", "failed"}:
            raise ValueError("auth_outcome must be success or failed")
        call_values = (self.call_direction, self.call_status, self.is_international, self.is_roaming)
        if self.event_type != "CALL" and any(value is not None for value in call_values):
            raise ValueError("call metadata is only valid for CALL events")
        if self.event_type not in {"SMS", "OTP_REQUEST"} and self.message_count is not None:
            raise ValueError("message_count is only valid for SMS or OTP_REQUEST events")
        if self.event_type not in {"OTP_REQUEST", "AUTHENTICATION"} and self.auth_outcome is not None:
            raise ValueError("auth_outcome is only valid for authentication events")
        return self

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
    resolution_outcome: str | None = None


class ActionIn(BaseModel):
    action: str
    reason: str = Field(min_length=3, max_length=500)


class SeedDatasetIn(BaseModel):
    count: int = Field(default=150000, ge=100000, le=300000)
    seed: int = Field(default=2026, ge=0, le=2_000_000_000)


class JobControlIn(BaseModel):
    action: str

    @field_validator("action")
    @classmethod
    def valid_action(cls, value):
        if value not in {"pause", "resume", "stop"}:
            raise ValueError("action must be pause, resume or stop")
        return value
