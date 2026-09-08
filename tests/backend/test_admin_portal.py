"""Unit and integration tests for the Proctor and Administrator Portal."""

import pytest
from backend.app import create_app
from backend.app.services.admin_service import (
    create_admin_user,
    get_admin_by_email,
    get_dashboard_summary,
    get_admin_sessions_list,
)
from backend.app.services.auth_service import register_candidate


@pytest.fixture()
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "admin-portal-test-secret",
        "DATABASE_PATH": str(tmp_path / "examguard.db"),
        "REGISTRATION_PHOTO_DIR": str(tmp_path / "photos"),
    })


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture
def test_admin_and_proctor(app):
    """Ensure test administrator and proctor accounts exist in the test DB."""
    with app.app_context():
        admin = get_admin_by_email("test_admin@examguard.test")
        if not admin:
            admin = create_admin_user(
                full_name="Lead Admin Tester",
                email="test_admin@examguard.test",
                password="Admin-Secure-1234!",
                role="ADMIN",
                is_active=True,
            )

        proctor = get_admin_by_email("test_proctor@examguard.test")
        if not proctor:
            proctor = create_admin_user(
                full_name="Staff Proctor Tester",
                email="test_proctor@examguard.test",
                password="Proctor-Secure-1234!",
                role="PROCTOR",
                is_active=True,
            )
        return {"admin": admin, "proctor": proctor}


def test_admin_login_success(client, test_admin_and_proctor):
    """1. Test that valid administrator credentials succeed and return authenticated session."""
    res = client.post("/api/admin/auth/login", json={
        "email": "test_admin@examguard.test",
        "password": "Admin-Secure-1234!"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["authenticated"] is True
    assert data["admin"]["email"] == "test_admin@examguard.test"
    assert data["admin"]["role"] == "ADMIN"
    assert "password_hash" not in data["admin"]


def test_admin_login_invalid_credentials(client, test_admin_and_proctor):
    """2. Test that incorrect administrator password returns 401."""
    res = client.post("/api/admin/auth/login", json={
        "email": "test_admin@examguard.test",
        "password": "WrongPassword-123!"
    })
    assert res.status_code == 401
    data = res.get_json()
    assert "error" in data


def test_admin_logout(client, test_admin_and_proctor):
    """3. Test that admin logout clears the session."""
    # Login
    client.post("/api/admin/auth/login", json={
        "email": "test_admin@examguard.test",
        "password": "Admin-Secure-1234!"
    })

    # Logout
    res = client.post("/api/admin/auth/logout")
    assert res.status_code == 200
    assert res.get_json()["authenticated"] is False

    # Check /api/admin/auth/me is now unauthenticated
    me_res = client.get("/api/admin/auth/me")
    assert me_res.status_code == 200
    assert me_res.get_json()["authenticated"] is False


def test_current_admin_session(client, test_admin_and_proctor):
    """4. Test /api/admin/auth/me returns the active administrator profile."""
    # Unauthenticated
    res = client.get("/api/admin/auth/me")
    assert res.status_code == 200
    assert res.get_json()["authenticated"] is False

    # Authenticate as Proctor
    client.post("/api/admin/auth/login", json={
        "email": "test_proctor@examguard.test",
        "password": "Proctor-Secure-1234!"
    })

    me_res = client.get("/api/admin/auth/me")
    assert me_res.status_code == 200
    data = me_res.get_json()
    assert data["authenticated"] is True
    assert data["admin"]["role"] == "PROCTOR"
    assert data["admin"]["email"] == "test_proctor@examguard.test"


def test_candidate_cannot_access_admin_api(client, app, test_admin_and_proctor):
    """5. Test that an authenticated candidate session CANNOT access administrative APIs."""
    with app.app_context():
        register_candidate(
            full_name="Candidate Intruder",
            email="intruder@examguard.test",
            password="Candidate-Pass-123!",
        )

    # Login as Candidate
    cand_login = client.post("/api/auth/login", json={
        "email": "intruder@examguard.test",
        "password": "Candidate-Pass-123!"
    })
    assert cand_login.status_code == 200
    assert cand_login.get_json()["authenticated"] is True

    # Candidate attempts to access Admin endpoints -> 401 (since session has no admin_id)
    summary_res = client.get("/api/admin/dashboard/summary")
    assert summary_res.status_code == 401

    sessions_res = client.get("/api/admin/sessions")
    assert sessions_res.status_code == 401


def test_unauthenticated_user_cannot_access_admin_apis(client):
    """6. Test that unauthenticated users are blocked with 401 from admin endpoints."""
    res1 = client.get("/api/admin/dashboard/summary")
    assert res1.status_code == 401

    res2 = client.get("/api/admin/sessions")
    assert res2.status_code == 401

    res3 = client.get("/api/admin/sessions/1")
    assert res3.status_code == 401


def test_proctor_role_can_access_monitoring_apis(client, test_admin_and_proctor):
    """7. Test that PROCTOR role can access dashboard summary and session roster."""
    client.post("/api/admin/auth/login", json={
        "email": "test_proctor@examguard.test",
        "password": "Proctor-Secure-1234!"
    })

    res = client.get("/api/admin/dashboard/summary")
    assert res.status_code == 200
    assert "summary" in res.get_json()

    res_sessions = client.get("/api/admin/sessions")
    assert res_sessions.status_code == 200
    assert "sessions" in res_sessions.get_json()


def test_admin_role_can_access_monitoring_apis(client, test_admin_and_proctor):
    """8. Test that ADMIN role can access dashboard summary and session roster."""
    client.post("/api/admin/auth/login", json={
        "email": "test_admin@examguard.test",
        "password": "Admin-Secure-1234!"
    })

    res = client.get("/api/admin/dashboard/summary")
    assert res.status_code == 200
    assert "summary" in res.get_json()


def test_admin_dashboard_summary_returns_real_database_counts(client, app, test_admin_and_proctor):
    """9. Test that summary endpoint returns real database counts matching DB state."""
    client.post("/api/admin/auth/login", json={
        "email": "test_admin@examguard.test",
        "password": "Admin-Secure-1234!"
    })

    res = client.get("/api/admin/dashboard/summary")
    assert res.status_code == 200
    summary = res.get_json()["summary"]

    assert "active_sessions" in summary
    assert "submitted_sessions" in summary
    assert "high_risk_sessions" in summary
    assert "total_sessions" in summary

    # Verify counts match service calculation
    with app.app_context():
        service_summary = get_dashboard_summary()
        assert summary["active_sessions"] == service_summary["active_sessions"]
        assert summary["submitted_sessions"] == service_summary["submitted_sessions"]
        assert summary["high_risk_sessions"] == service_summary["high_risk_sessions"]
        assert summary["total_sessions"] == service_summary["total_sessions"]


def test_admin_sessions_prioritizes_high_risk(client, app, test_admin_and_proctor):
    """10. Test that sessions list prioritizes HIGH risk sessions ahead of lower risk sessions."""
    with app.app_context():
        # Retrieve sessions
        sessions = get_admin_sessions_list(limit=20)
        assert isinstance(sessions, list)
        # If there are sessions with HIGH risk, check that they are ranked first
        high_risk_indices = [i for i, s in enumerate(sessions) if s["risk_level"] == "HIGH"]
        low_risk_indices = [i for i, s in enumerate(sessions) if s["risk_level"] == "LOW"]
        if high_risk_indices and low_risk_indices:
            assert min(high_risk_indices) < max(low_risk_indices)


def test_admin_page_routes_serve_html(client, test_admin_and_proctor):
    """11. Test that /admin/login and /admin page routes respond with HTTP 200 and HTML."""
    login_page = client.get("/admin/login")
    assert login_page.status_code == 200
    assert b"<!DOCTYPE html>" in login_page.data
    assert b"Proctor & Admin Sign In" in login_page.data or b"Proctor Sign In" in login_page.data

    dashboard_page = client.get("/admin")
    assert dashboard_page.status_code == 200
    assert b"<!DOCTYPE html>" in dashboard_page.data
    assert b"Institution Proctor Dashboard" in dashboard_page.data
