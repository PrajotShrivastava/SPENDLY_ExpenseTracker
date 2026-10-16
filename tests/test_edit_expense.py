from datetime import date, timedelta

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


@pytest.fixture
def logged_in(client):
    client.post("/login", data={"email": db.DEMO_EMAIL, "password": db.DEMO_PASSWORD})
    return client


@pytest.fixture
def expense():
    """The demo user's 'Groceries' expense (₹450, Food, 2026-10-01)."""
    with db.get_db() as conn:
        return conn.execute("SELECT * FROM expenses WHERE description = 'Groceries'").fetchone()


@pytest.fixture
def other_users_expense():
    user_id = db.create_user("Other", "other@example.com", "password123")
    expense_id = db.add_expense(user_id, 999, "Bills", "2026-10-01", "Their bill")
    with db.get_db() as conn:
        return conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()


def fetch(expense_id):
    with db.get_db() as conn:
        return conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()


def edit_form(**overrides):
    form = {"amount": "500", "category": "Food", "date": "2026-10-02", "description": "Weekly groceries"}
    form.update(overrides)
    return form


# ------------------------------------------------------------------ #
# Access                                                              #
# ------------------------------------------------------------------ #

def test_edit_requires_login(client, expense):
    resp = client.get(f"/expenses/{expense['id']}/edit")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


def test_edit_missing_expense_is_404(logged_in):
    assert logged_in.get("/expenses/99999/edit").status_code == 404


def test_cannot_view_or_edit_another_users_expense(logged_in, other_users_expense):
    url = f"/expenses/{other_users_expense['id']}/edit"
    assert logged_in.get(url).status_code == 404
    assert logged_in.post(url, data=edit_form(amount="1")).status_code == 404
    assert fetch(other_users_expense["id"])["amount"] == 999


# ------------------------------------------------------------------ #
# Form                                                                #
# ------------------------------------------------------------------ #

def test_edit_form_is_prefilled(logged_in, expense):
    html = logged_in.get(f"/expenses/{expense['id']}/edit").get_data(as_text=True)
    assert "Edit expense" in html
    assert "Save changes" in html
    assert 'value="450"' in html
    assert 'value="2026-10-01"' in html
    assert 'value="Groceries"' in html
    assert '<option value="Food" selected>' in html
    assert f'action="/expenses/{expense["id"]}/edit"' in html


def test_edit_form_keeps_paise(logged_in):
    user = db.get_user_by_email(db.DEMO_EMAIL)
    expense_id = db.add_expense(user["id"], 99.5, "Food", "2026-10-01")
    html = logged_in.get(f"/expenses/{expense_id}/edit").get_data(as_text=True)
    assert 'value="99.50"' in html


def test_profile_links_to_edit(logged_in):
    html = logged_in.get("/profile").get_data(as_text=True)
    assert "/edit" in html


# ------------------------------------------------------------------ #
# Saving                                                              #
# ------------------------------------------------------------------ #

def test_edit_saves_changes_and_redirects(logged_in, expense):
    resp = logged_in.post(f"/expenses/{expense['id']}/edit", data=edit_form(category="Shopping"))
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")

    updated = fetch(expense["id"])
    assert updated["amount"] == 500
    assert updated["category"] == "Shopping"
    assert updated["date"] == "2026-10-02"
    assert updated["description"] == "Weekly groceries"
    assert updated["user_id"] == expense["user_id"]
    assert updated["created_at"] == expense["created_at"]

    assert "Updated Weekly groceries." in logged_in.get("/profile").get_data(as_text=True)


def test_edit_only_changes_that_expense(logged_in, expense):
    with db.get_db() as conn:
        before = conn.execute("SELECT * FROM expenses WHERE id != ? ORDER BY id", (expense["id"],)).fetchall()
    logged_in.post(f"/expenses/{expense['id']}/edit", data=edit_form())
    with db.get_db() as conn:
        after = conn.execute("SELECT * FROM expenses WHERE id != ? ORDER BY id", (expense["id"],)).fetchall()
    assert [tuple(r) for r in before] == [tuple(r) for r in after]


def test_clearing_description_stores_null(logged_in, expense):
    logged_in.post(f"/expenses/{expense['id']}/edit", data=edit_form(description=""))
    assert fetch(expense["id"])["description"] is None


@pytest.mark.parametrize("overrides,message", [
    ({"amount": "0"}, "greater than zero"),
    ({"category": "Bribes"}, "choose a category"),
    ({"date": (date.today() + timedelta(days=1)).isoformat()}, "in the future"),
])
def test_invalid_edit_is_rejected_and_keeps_input(logged_in, expense, overrides, message):
    resp = logged_in.post(f"/expenses/{expense['id']}/edit", data=edit_form(**overrides))
    html = resp.get_data(as_text=True)
    assert resp.status_code == 400
    assert message in html
    assert 'value="Weekly groceries"' in html
    assert "Save changes" in html
    assert tuple(fetch(expense["id"])) == tuple(expense)
