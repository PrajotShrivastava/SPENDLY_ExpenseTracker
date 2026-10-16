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
# Users                                                               #
# ------------------------------------------------------------------ #

def get_user_by_id(user_id):
    with get_db() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_user_by_email(email):
    with get_db() as conn:
        return conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


def create_user(name, email, password):
    """Insert a user and return their id. Raises sqlite3.IntegrityError if the email is taken."""
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, hash_password(password)),
        )
        return cur.lastrowid


# ------------------------------------------------------------------ #
# Expenses                                                            #
# ------------------------------------------------------------------ #

def add_expense(user_id, amount, category, date, description=None):
    """Insert an expense and return its id."""
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, date, description),
        )
        return cur.lastrowid


def get_expense(expense_id, user_id):
    """Return the expense only if it belongs to user_id, otherwise None."""
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id)
        ).fetchone()


def update_expense(expense_id, user_id, amount, category, date, description=None):
    """Update an expense the user owns. Returns True if a row was changed."""
    with get_db() as conn:
        cur = conn.execute(
            """
            UPDATE expenses
            SET amount = ?, category = ?, date = ?, description = ?
            WHERE id = ? AND user_id = ?
            """,
            (amount, category, date, description, expense_id, user_id),
        )
        return cur.rowcount == 1


# ------------------------------------------------------------------ #
# Expense summaries                                                   #
# ------------------------------------------------------------------ #

def get_expense_summary(user_id):
    """Totals across all time and for the current calendar month."""
    with get_db() as conn:
        return conn.execute(
            """
            SELECT COUNT(*)                                                         AS count,
                   COALESCE(SUM(amount), 0)                                         AS total,
                   COALESCE(SUM(CASE WHEN date >= date('now', 'start of month')
                                     THEN amount END), 0)                           AS month_total,
                   COUNT(CASE WHEN date >= date('now', 'start of month') THEN 1 END) AS month_count
            FROM expenses
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()


def get_category_totals(user_id):
    with get_db() as conn:
        return conn.execute(
            """
            SELECT category, SUM(amount) AS total
            FROM expenses
            WHERE user_id = ?
            GROUP BY category
            ORDER BY total DESC
            """,
            (user_id,),
        ).fetchall()


def get_recent_expenses(user_id, limit=5):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()


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
