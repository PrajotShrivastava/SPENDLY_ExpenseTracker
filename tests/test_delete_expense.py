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
    return db.add_expense(user_id, 999, "Bills", "2026-10-01", "Their bill")


def exists(expense_id):
    with db.get_db() as conn:
        return conn.execute("SELECT 1 FROM expenses WHERE id = ?", (expense_id,)).fetchone() is not None


def expense_count():
    with db.get_db() as conn:
        return conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]


# ------------------------------------------------------------------ #
# Access                                                              #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("method", ["get", "post"])
def test_delete_requires_login(client, expense, method):
    resp = getattr(client, method)(f"/expenses/{expense['id']}/delete")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")
    assert exists(expense["id"])


@pytest.mark.parametrize("method", ["get", "post"])
def test_delete_missing_expense_is_404(logged_in, method):
    assert getattr(logged_in, method)("/expenses/99999/delete").status_code == 404


@pytest.mark.parametrize("method", ["get", "post"])
def test_cannot_delete_another_users_expense(logged_in, other_users_expense, method):
    resp = getattr(logged_in, method)(f"/expenses/{other_users_expense}/delete")
    assert resp.status_code == 404
    assert exists(other_users_expense)


# ------------------------------------------------------------------ #
# Confirmation                                                        #
# ------------------------------------------------------------------ #

def test_get_shows_confirmation_without_deleting(logged_in, expense):
    resp = logged_in.get(f"/expenses/{expense['id']}/delete")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "Delete this expense?" in html
    assert "Groceries" in html
    assert "₹450" in html
    assert f'action="/expenses/{expense["id"]}/delete"' in html
    assert 'method="POST"' in html
    assert exists(expense["id"])


def test_edit_page_links_to_delete(logged_in, expense):
    html = logged_in.get(f"/expenses/{expense['id']}/edit").get_data(as_text=True)
    assert f'href="/expenses/{expense["id"]}/delete"' in html


def test_add_page_has_no_delete_link(logged_in):
    assert "/delete" not in logged_in.get("/expenses/add").get_data(as_text=True)


def test_profile_links_to_delete(logged_in):
    assert "/delete" in logged_in.get("/profile").get_data(as_text=True)


# ------------------------------------------------------------------ #
# Deleting                                                            #
# ------------------------------------------------------------------ #

def test_post_deletes_and_redirects_with_message(logged_in, expense):
    before = expense_count()
    resp = logged_in.post(f"/expenses/{expense['id']}/delete")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")
    assert not exists(expense["id"])
    assert expense_count() == before - 1
    assert "Deleted Groceries (₹450)." in logged_in.get("/profile").get_data(as_text=True)


def test_deleting_twice_is_404(logged_in, expense):
    logged_in.post(f"/expenses/{expense['id']}/delete")
    assert logged_in.post(f"/expenses/{expense['id']}/delete").status_code == 404


def test_deleted_expense_disappears_from_totals(logged_in, expense):
    user = db.get_user_by_email(db.DEMO_EMAIL)
    before = db.get_expense_summary(user["id"])
    logged_in.post(f"/expenses/{expense['id']}/delete")
    after = db.get_expense_summary(user["id"])
    assert after["total"] == before["total"] - 450
    assert after["count"] == before["count"] - 1


def test_deleting_last_expense_shows_empty_state(logged_in):
    with db.get_db() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM expenses")]
    for expense_id in ids:
        logged_in.post(f"/expenses/{expense_id}/delete")
    assert "No expenses yet" in logged_in.get("/profile").get_data(as_text=True)
