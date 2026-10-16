import pytest

from app import app as flask_app, format_inr
from database import db


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE", str(tmp_path / "test.db"))
    db.init_db()
    db.seed_db()
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client


def login(client, email=db.DEMO_EMAIL, password=db.DEMO_PASSWORD):
    return client.post("/login", data={"email": email, "password": password})


def add_expense(user_id, amount, category, date, description=None):
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, date, description),
        )


# ------------------------------------------------------------------ #
# Access                                                              #
# ------------------------------------------------------------------ #

def test_profile_requires_login(client):
    resp = client.get("/profile")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


def test_profile_with_deleted_user_logs_out(client):
    login(client)
    with db.get_db() as conn:
        conn.execute("DELETE FROM users")
    resp = client.get("/profile")
    assert resp.headers["Location"].endswith("/login")
    with client.session_transaction() as sess:
        assert "user_id" not in sess


# ------------------------------------------------------------------ #
# Content                                                             #
# ------------------------------------------------------------------ #

def test_profile_shows_user_details(client):
    login(client)
    html = client.get("/profile").get_data(as_text=True)
    assert "Demo User" in html
    assert db.DEMO_EMAIL in html
    assert "Member since" in html


def test_profile_shows_totals_and_categories(client):
    login(client)
    html = client.get("/profile").get_data(as_text=True)
    total = sum(e[0] for e in db.SAMPLE_EXPENSES)
    assert format_inr(total) in html
    for category in {e[1] for e in db.SAMPLE_EXPENSES}:
        assert category in html


def test_profile_lists_five_most_recent_expenses(client):
    login(client)
    html = client.get("/profile").get_data(as_text=True)
    newest_first = sorted(db.SAMPLE_EXPENSES, key=lambda e: e[2], reverse=True)
    for _, _, _, description in newest_first[:5]:
        assert description in html
    for _, _, _, description in newest_first[5:]:
        assert description not in html


def test_month_total_ignores_older_expenses(client):
    user = db.get_user_by_email(db.DEMO_EMAIL)
    before = db.get_expense_summary(user["id"])
    add_expense(user["id"], 777, "Other", "2000-01-01", "Ancient expense")
    after = db.get_expense_summary(user["id"])
    assert after["total"] == before["total"] + 777
    assert after["count"] == before["count"] + 1
    assert after["month_total"] == before["month_total"]
    assert after["month_count"] == before["month_count"]


def test_month_total_includes_today(client):
    user = db.get_user_by_email(db.DEMO_EMAIL)
    before = db.get_expense_summary(user["id"])
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date) VALUES (?, 100, 'Food', date('now'))",
            (user["id"],),
        )
    after = db.get_expense_summary(user["id"])
    assert after["month_total"] == before["month_total"] + 100
    assert after["month_count"] == before["month_count"] + 1


def test_profile_only_shows_own_expenses(client):
    db.create_user("Other Person", "other@example.com", "password123")
    other = db.get_user_by_email("other@example.com")
    add_expense(other["id"], 55555, "Food", "2026-10-01", "Someone else's lunch")
    login(client)
    html = client.get("/profile").get_data(as_text=True)
    assert "Someone else" not in html
    assert format_inr(55555) not in html


def test_profile_empty_state_for_new_user(client):
    client.post("/register", data={"name": "New Person", "email": "new@example.com", "password": "password123"})
    html = client.get("/profile").get_data(as_text=True)
    assert "No expenses yet" in html
    assert "₹0" in html


# ------------------------------------------------------------------ #
# Formatting                                                          #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("amount,expected", [
    (0, "₹0"),
    (999, "₹999"),
    (9047, "₹9,047"),
    (123456.5, "₹1,23,456.50"),
    (12345678, "₹1,23,45,678"),
    (-1500, "-₹1,500"),
])
def test_format_inr(amount, expected):
    assert format_inr(amount) == expected
