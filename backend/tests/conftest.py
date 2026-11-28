import os

os.environ["TG_DATABASE_URL"] = "sqlite:///./test_teleguard.db"
os.environ["TG_SECRET_KEY"] = "test-only-secret-key-at-least-32-bytes"
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine, SessionLocal
from app.models import User
from app.security import hash_password


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.add(
            User(
                username="admin",
                password_hash=hash_password("test-password-123"),
                role="Administrator",
            )
        )
        db.add(
            User(
                username="auditor", password_hash=hash_password("test-password-123"), role="Auditor"
            )
        )
        db.commit()
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(engine)


@pytest.fixture
def token(client):
    response = client.post(
        "/api/auth/login", json={"username": "admin", "password": "test-password-123"}
    )
    return response.json()["access_token"]
