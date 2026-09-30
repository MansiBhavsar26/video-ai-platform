from fastapi.testclient import TestClient

from app import main


class FakeSession:
    def __init__(self, error=None):
        self.error = error

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, statement):
        if self.error:
            raise self.error


def test_health_reports_database_available(monkeypatch):
    monkeypatch.setattr(main, "SessionLocal", lambda: FakeSession())

    response = TestClient(main.app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_reports_database_unavailable_without_internal_details(monkeypatch):
    monkeypatch.setattr(
        main,
        "SessionLocal",
        lambda: FakeSession(RuntimeError("private database connection detail")),
    )

    response = TestClient(main.app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "database": "unavailable"}
    assert "private database connection detail" not in response.text
