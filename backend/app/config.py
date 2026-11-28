from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./teleguard.db"
    secret_key: str = "local-only-change-me-use-32-bytes-min"
    token_minutes: int = 720
    api_workers: int = Field(default=1, ge=1, le=8)
    model_path: str = "artifacts/fraud-model.joblib"
    model_version: str = "synthetic-rf-v1"
    risk_policy_version: str = "risk-v2"
    risk_supervised_weight: float = Field(default=0.62, ge=0, le=1)
    risk_anomaly_weight: float = Field(default=0.18, ge=0, le=1)
    risk_graph_weight: float = Field(default=0.08, ge=0, le=1)
    risk_rule_weight: float = Field(default=0.12, ge=0, le=1)
    incident_risk_threshold: float = Field(default=0.35, ge=0, le=1)
    classification_threshold: float = Field(default=0.5, gt=0, lt=1)
    case_max_age_minutes: int = Field(default=120, ge=1, le=1440)
    case_max_events: int = Field(default=40, ge=2, le=200)
    case_cross_entity_min_risk: float = Field(default=0.60, ge=0, le=1)
    cors_origins: str = "http://localhost:5173"
    enable_api_docs: bool = True
    model_config = SettingsConfigDict(env_prefix="TG_", env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def risk_weights_sum_to_one(self):
        if len(self.secret_key.encode("utf-8")) < 32:
            raise ValueError("secret_key must contain at least 32 bytes")
        weights = (
            self.risk_supervised_weight
            + self.risk_anomaly_weight
            + self.risk_graph_weight
            + self.risk_rule_weight
        )
        if abs(weights - 1.0) > 1e-6:
            raise ValueError("risk signal weights must sum to 1.0")
        return self


settings = Settings()
