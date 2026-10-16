import sqlite3

import pytest
from werkzeug.security import check_password_hash

from database import db


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE", str(tmp_path / "test.db"))
    db.init_db()


def test_init_db_creates_tables():
    with db.get_db() as conn:
        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"users", "expenses"} <= tables


def test_init_db_is_idempotent():
    db.init_db()
    db.init_db()


def test_seed_db_inserts_demo_user_once():
    db.seed_db()
    db.seed_db()
    with db.get_db() as conn:
        users = conn.execute("SELECT * FROM users").fetchall()
        expense_count = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    assert len(users) == 1
    assert users[0]["email"] == db.DEMO_EMAIL
    assert check_password_hash(users[0]["password_hash"], db.DEMO_PASSWORD)
    assert expense_count == len(db.SAMPLE_EXPENSES)


def test_foreign_keys_enforced():
    with pytest.raises(sqlite3.IntegrityError):
        with db.get_db() as conn:
            conn.execute(
                "INSERT INTO expenses (user_id, amount, category, date) VALUES (999, 10, 'Food', '2026-10-01')"
            )


def test_deleting_user_deletes_their_expenses():
    db.seed_db()
    with db.get_db() as conn:
        conn.execute("DELETE FROM users")
    with db.get_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 0


def test_email_must_be_unique():
    db.seed_db()
    with pytest.raises(sqlite3.IntegrityError):
        with db.get_db() as conn:
            conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES ('X', ?, 'h')", (db.DEMO_EMAIL,)
            )
