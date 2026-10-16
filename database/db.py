import os
import sqlite3

from werkzeug.security import generate_password_hash

# Lives in the project root (already listed in .gitignore). Set SPENDLY_DB
# to point somewhere else, e.g. a temporary file in tests.
DATABASE = os.environ.get(
    "SPENDLY_DB",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "expense_tracker.db"),
)

CATEGORIES = ["Food", "Travel", "Bills", "Shopping", "Health", "Entertainment", "Other"]


def hash_password(password):
    # Werkzeug defaults to scrypt, which the macOS system Python (LibreSSL) lacks.
    return generate_password_hash(password, method="pbkdf2:sha256")


# ------------------------------------------------------------------ #
# Connection                                                          #
# ------------------------------------------------------------------ #

def get_db():
    """Return a SQLite connection whose rows behave like dicts."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ------------------------------------------------------------------ #
# Schema                                                              #
# ------------------------------------------------------------------ #

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount      REAL    NOT NULL CHECK (amount > 0),
    category    TEXT    NOT NULL,
    date        TEXT    NOT NULL,
    description TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_expenses_user_date ON expenses (user_id, date);
"""


def init_db():
    """Create all tables. Safe to call on every start-up."""
    with get_db() as conn:
        conn.executescript(SCHEMA)


# ------------------------------------------------------------------ #
# Sample data                                                         #
# ------------------------------------------------------------------ #

DEMO_EMAIL = "demo@spendly.app"
DEMO_PASSWORD = "demo1234"

SAMPLE_EXPENSES = [
    # (amount, category, date, description)
    (450.00,  "Food",          "2026-10-01", "Groceries"),
    (1200.00, "Bills",         "2026-10-02", "Electricity bill"),
    (180.00,  "Travel",        "2026-10-03", "Auto to office"),
    (650.00,  "Food",          "2026-10-05", "Dinner with friends"),
    (2499.00, "Shopping",      "2026-10-06", "Running shoes"),
    (399.00,  "Entertainment", "2026-10-08", "Movie tickets"),
    (850.00,  "Health",        "2026-10-09", "Pharmacy"),
    (999.00,  "Bills",         "2026-10-10", "Internet"),
    (320.00,  "Food",          "2026-10-12", "Lunch"),
    (1500.00, "Travel",        "2026-10-14", "Train tickets"),
]


def seed_db():
    """Insert a demo user with sample expenses. Does nothing if already seeded."""
    with get_db() as conn:
        if conn.execute("SELECT 1 FROM users WHERE email = ?", (DEMO_EMAIL,)).fetchone():
            return

        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Demo User", DEMO_EMAIL, hash_password(DEMO_PASSWORD)),
        )
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
            [(cur.lastrowid, *row) for row in SAMPLE_EXPENSES],
        )
