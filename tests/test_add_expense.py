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


def valid_form(**overrides):
    form = {
        "amount": "450",
        "category": "Food",
        "date": date.today().isoformat(),
        "description": "Groceries",
    }
    form.update(overrides)
    return form


def expense_count():
    with db.get_db() as conn:
        return conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]


def latest_expense():
    with db.get_db() as conn:
        return conn.execute("SELECT * FROM expenses ORDER BY id DESC LIMIT 1").fetchone()


# ------------------------------------------------------------------ #
# Access and form                                                     #
# ------------------------------------------------------------------ #

def test_add_expense_requires_login(client):
    for method in (client.get, client.post):
        resp = method("/expenses/add")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/login")


def test_form_defaults_to_today_and_lists_categories(logged_in):
    html = logged_in.get("/expenses/add").get_data(as_text=True)
    assert f'value="{date.today().isoformat()}"' in html
    for category in db.CATEGORIES:
        assert f'<option value="{category}"' in html


def test_profile_links_to_add_expense(logged_in):
    assert 'href="/expenses/add"' in logged_in.get("/profile").get_data(as_text=True)


# ------------------------------------------------------------------ #
# Saving                                                              #
# ------------------------------------------------------------------ #

def test_add_expense_saves_and_redirects_with_message(logged_in):
    before = expense_count()
    resp = logged_in.post("/expenses/add", data=valid_form(amount="1,250.5"))
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")
    assert expense_count() == before + 1

    e = latest_expense()
    user = db.get_user_by_email(db.DEMO_EMAIL)
    assert e["user_id"] == user["id"]
    assert e["amount"] == 1250.5
    assert e["category"] == "Food"
    assert e["description"] == "Groceries"

    html = logged_in.get("/profile").get_data(as_text=True)
    assert "Added ₹1,250.50 for Food." in html


def test_flash_message_only_shows_once(logged_in):
    logged_in.post("/expenses/add", data=valid_form())
    assert "Added ₹450 for Food." in logged_in.get("/profile").get_data(as_text=True)
    assert "Added ₹450" not in logged_in.get("/profile").get_data(as_text=True)


def test_blank_description_is_stored_as_null(logged_in):
    logged_in.post("/expenses/add", data=valid_form(description="   "))
    assert latest_expense()["description"] is None


def test_amount_is_rounded_to_paise(logged_in):
    logged_in.post("/expenses/add", data=valid_form(amount="99.999"))
    assert latest_expense()["amount"] == 100.0


def test_expense_belongs_to_logged_in_user_only(logged_in):
    db.create_user("Other", "other@example.com", "password123")
    logged_in.post("/expenses/add", data=valid_form(user_id="999"))
    user = db.get_user_by_email(db.DEMO_EMAIL)
    assert latest_expense()["user_id"] == user["id"]


# ------------------------------------------------------------------ #
# Validation                                                          #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("overrides,message", [
    ({"amount": ""}, "valid amount"),
    ({"amount": "abc"}, "valid amount"),
    ({"amount": "NaN"}, "greater than zero"),
    ({"amount": "inf"}, "valid amount"),
    ({"amount": "0"}, "greater than zero"),
    ({"amount": "-50"}, "greater than zero"),
    ({"amount": "10000000.01"}, "more than ₹1,00,00,000"),
    ({"category": ""}, "choose a category"),
    ({"category": "Bribes"}, "choose a category"),
    ({"date": ""}, "valid date"),
    ({"date": "2026-02-30"}, "valid date"),
    ({"date": (date.today() + timedelta(days=1)).isoformat()}, "in the future"),
    ({"description": "x" * 201}, "200 characters"),
])
def test_invalid_input_is_rejected(logged_in, overrides, message):
    before = expense_count()
    resp = logged_in.post("/expenses/add", data=valid_form(**overrides))
    assert resp.status_code == 400
    assert message in resp.get_data(as_text=True)
    assert expense_count() == before


def test_form_keeps_values_after_error(logged_in):
    resp = logged_in.post("/expenses/add", data=valid_form(amount="0", category="Travel", description="Cab home"))
    html = resp.get_data(as_text=True)
    assert 'value="Cab home"' in html
    assert '<option value="Travel" selected>' in html
