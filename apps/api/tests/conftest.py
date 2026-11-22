"""Test fixtures: isolated SQLite DB + storage per session, demo users, authenticated clients."""
from __future__ import annotations

import os
import tempfile
import uuid

import os

import pytest

_TMP = tempfile.mkdtemp(prefix="ps05x_test_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_TMP, "test.db").replace("\\", "/")
os.environ["STORAGE_DIR"] = os.path.join(_TMP, "data")
os.environ["BENCHMARK_STORE_DIR"] = os.path.join(_TMP, "sealed")
os.environ["JWT_SECRET"] = "test-secret-" + uuid.uuid4().hex
os.environ["DEMO_ANALYST_PASSWORD"] = "analyst-test-pass"
os.environ["DEMO_SUPERVISOR_PASSWORD"] = "supervisor-test-pass"
os.environ["DEMO_ADMIN_PASSWORD"] = "admin-test-pass"
os.environ["CORS_ORIGINS"] = "http://localhost:3000"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Role, User  # noqa: E402


# Rate limits are real and tested in tests/test_rate_limiting.py, which turns them on for itself. Everywhere else
# they are off, so a limit cannot mask an unrelated failure in a suite that legitimately generates many cases.
os.environ.setdefault("RATE_LIMIT_ENABLED", "0")


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        with SessionLocal() as db:
            db.add(User(email="other@demo.local", display_name="Other Analyst", password_hash=hash_password("other-test-pass"), role=Role.analyst))
            db.commit()
        yield c


def _login(client: TestClient, email: str, password: str) -> dict:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def analyst(client):
    return _login(client, "analyst@demo.local", "analyst-test-pass")


@pytest.fixture(scope="session")
def other_analyst(client):
    return _login(client, "other@demo.local", "other-test-pass")


@pytest.fixture(scope="session")
def supervisor(client):
    return _login(client, "supervisor@demo.local", "supervisor-test-pass")


@pytest.fixture(scope="session")
def admin(client):
    return _login(client, "admin@demo.local", "admin-test-pass")


@pytest.fixture(scope="session")
def synthetic_case(client, analyst):
    r = client.post("/api/synthetic/generate", json={"scenario_type": "phishing_to_mule", "difficulty": "adversarial", "size": "small", "seed": 11}, headers=analyst)
    assert r.status_code == 201, r.text
    return r.json()
