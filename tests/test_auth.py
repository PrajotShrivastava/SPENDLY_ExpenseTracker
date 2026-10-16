import pytest

from app import app as flask_app
from database import db


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE", str(tmp_path / "test.db"))
    db.init_db()
    db.seed_db()
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client


def register(client, name="Asha Rao", email="asha@example.com", password="secret123"):
    return client.post("/register", data={"name": name, "email": email, "password": password})


def login(client, email=db.DEMO_EMAIL, password=db.DEMO_PASSWORD):
    return client.post("/login", data={"email": email, "password": password})


# ------------------------------------------------------------------ #
# Register                                                            #
# ------------------------------------------------------------------ #

def test_register_creates_user_and_logs_in(client):
    resp = register(client)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")
    user = db.get_user_by_email("asha@example.com")
    assert user["name"] == "Asha Rao"
    assert user["password_hash"] != "secret123"
    with client.session_transaction() as sess:
        assert sess["user_id"] == user["id"]


def test_register_normalises_email(client):
    register(client, email="  Asha@Example.COM ")
    assert db.get_user_by_email("asha@example.com") is not None


def test_register_rejects_duplicate_email(client):
    resp = register(client, email=db.DEMO_EMAIL.upper())
    assert resp.status_code == 400
    assert "already exists" in resp.get_data(as_text=True)


def test_register_rejects_short_password(client):
    resp = register(client, password="short")
    assert resp.status_code == 400
    assert "at least 8 characters" in resp.get_data(as_text=True)
    assert db.get_user_by_email("asha@example.com") is None


def test_register_rejects_missing_fields(client):
    resp = register(client, name="   ")
    assert resp.status_code == 400
    assert "fill in all fields" in resp.get_data(as_text=True)


# ------------------------------------------------------------------ #
# Login                                                               #
# ------------------------------------------------------------------ #

def test_login_with_demo_user(client):
    resp = login(client)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")
    with client.session_transaction() as sess:
        assert sess["user_name"] == "Demo User"


def test_login_is_case_insensitive_on_email(client):
    assert login(client, email=db.DEMO_EMAIL.upper()).status_code == 302


@pytest.mark.parametrize("email,password", [
    (db.DEMO_EMAIL, "wrong-password"),
    ("nobody@example.com", db.DEMO_PASSWORD),
])
def test_login_rejects_bad_credentials(client, email, password):
    resp = login(client, email=email, password=password)
    assert resp.status_code == 401
    assert "Invalid email or password." in resp.get_data(as_text=True)
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_newly_registered_user_can_log_in(client):
    register(client)
    with client.session_transaction() as sess:
        sess.clear()
    assert login(client, email="asha@example.com", password="secret123").status_code == 302


@pytest.mark.parametrize("path", ["/login", "/register"])
def test_logged_in_user_is_redirected_away_from_auth_pages(client, path):
    login(client)
    resp = client.get(path)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")


# ------------------------------------------------------------------ #
# Logout and navbar                                                   #
# ------------------------------------------------------------------ #

def test_logout_clears_session_and_redirects_home(client):
    login(client)
    resp = client.get("/logout")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_logout_when_logged_out_is_harmless(client):
    assert client.get("/logout").status_code == 302


def test_navbar_shows_sign_in_when_logged_out(client):
    html = client.get("/").get_data(as_text=True)
    assert 'href="/login"' in html
    assert "Log out" not in html


def test_navbar_shows_user_and_logout_when_logged_in(client):
    login(client)
    html = client.get("/").get_data(as_text=True)
    assert "Demo User" in html
    assert 'href="/logout"' in html
    assert 'href="/login"' not in html


def test_navbar_escapes_user_name(client):
    register(client, name="<script>alert(1)</script>")
    html = client.get("/").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
