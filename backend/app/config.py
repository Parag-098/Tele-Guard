from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./teleguard.db"
    secret_key: str = "local-only-change-me"
    token_minutes: int = 720
    model_path: str = "artifacts/fraud-model.joblib"
    model_version: str = "synthetic-rf-v1"
    risk_policy_version: str = "risk-v1"
    risk_supervised_weight: float = Field(default=0.62, ge=0, le=1)
    risk_anomaly_weight: float = Field(default=0.18, ge=0, le=1)
    risk_graph_weight: float = Field(default=0.08, ge=0, le=1)
    risk_rule_weight: float = Field(default=0.12, ge=0, le=1)
    incident_risk_threshold: float = Field(default=0.35, ge=0, le=1)
    cors_origins: str = "http://localhost:5173"
    model_config = SettingsConfigDict(env_prefix="TG_", env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def risk_weights_sum_to_one(self):
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
