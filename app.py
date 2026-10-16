import os
import sqlite3
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import (
    CATEGORIES,
    add_expense as insert_expense,
    create_user,
    delete_expense as remove_expense,
    get_category_totals,
    get_expense,
    get_expense_summary,
    get_recent_expenses,
    get_user_by_email,
    get_user_by_id,
    init_db,
    seed_db,
    update_expense,
)

app = Flask(__name__)
# Set SECRET_KEY in the environment for anything beyond local development.
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-insecure-key")

MIN_PASSWORD_LENGTH = 8
MAX_EXPENSE_AMOUNT = Decimal("10000000")  # ₹1 crore — guards against typos
MAX_DESCRIPTION_LENGTH = 200

init_db()
seed_db()


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def parse_expense_form(form):
    """Validate an expense form. Returns (values, error); exactly one is None."""
    raw_amount = form.get("amount", "").strip().replace(",", "")
    category = form.get("category", "")
    raw_date = form.get("date", "").strip()
    description = form.get("description", "").strip()

    try:
        amount = Decimal(raw_amount).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None, "Please enter a valid amount."
    if not amount.is_finite() or amount <= 0:
        return None, "Amount must be greater than zero."
    if amount > MAX_EXPENSE_AMOUNT:
        return None, f"Amount can't be more than {format_inr(MAX_EXPENSE_AMOUNT)}."

    if category not in CATEGORIES:
        return None, "Please choose a category."

    try:
        spent_on = date.fromisoformat(raw_date)
    except ValueError:
        return None, "Please enter a valid date."
    if spent_on > date.today():
        return None, "Date can't be in the future."

    if len(description) > MAX_DESCRIPTION_LENGTH:
        return None, f"Description must be {MAX_DESCRIPTION_LENGTH} characters or fewer."

    return {
        "amount": float(amount),
        "category": category,
        "date": spent_on.isoformat(),
        "description": description or None,
    }, None


@app.template_filter("inr")
def format_inr(amount):
    """Format a number as rupees with Indian digit grouping, e.g. 123456.5 -> ₹1,23,456.50."""
    rupees, paise = f"{abs(amount):.2f}".split(".")
    if len(rupees) > 3:
        head, tail = rupees[:-3], rupees[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        rupees = ",".join([head] + groups) + "," + tail
    sign = "-" if amount < 0 else ""
    return f"{sign}₹{rupees}" if paise == "00" else f"{sign}₹{rupees}.{paise}"


@app.template_filter("date_format")
def format_date(value, fmt="%d %b %Y"):
    """Format a SQLite 'YYYY-MM-DD[ HH:MM:SS]' string."""
    return datetime.fromisoformat(value).strftime(fmt)


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


def log_in(user_id, name):
    session.clear()
    session["user_id"] = user_id
    session["user_name"] = name


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))
    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    error = None
    if not name or not email or not password:
        error = "Please fill in all fields."
    elif "@" not in email:
        error = "Please enter a valid email address."
    elif len(password) < MIN_PASSWORD_LENGTH:
        error = f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    else:
        try:
            user_id = create_user(name, email, password)
        except sqlite3.IntegrityError:
            error = "An account with this email already exists."

    if error:
        return render_template("register.html", error=error), 400

    log_in(user_id, name)
    return redirect(url_for("profile"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    user = get_user_by_email(email)
    # Same message either way so the form doesn't reveal which emails are registered.
    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Invalid email or password."), 401

    log_in(user["id"], user["name"])
    return redirect(url_for("profile"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/profile")
@login_required
def profile():
    user = get_user_by_id(session["user_id"])
    if user is None:
        # The account was deleted while this session was still active.
        session.clear()
        return redirect(url_for("login"))

    categories = get_category_totals(user["id"])
    top_total = categories[0]["total"] if categories else 0
    return render_template(
        "profile.html",
        user=user,
        summary=get_expense_summary(user["id"]),
        categories=categories,
        top_total=top_total,
        recent=get_recent_expenses(user["id"]),
    )


@app.route("/expenses/add", methods=["GET", "POST"])
@login_required
def add_expense():
    form = request.form if request.method == "POST" else {"date": date.today().isoformat()}

    if request.method == "POST":
        values, error = parse_expense_form(request.form)
        if error is None:
            insert_expense(session["user_id"], **values)
            flash(f"Added {format_inr(values['amount'])} for {values['category']}.")
            return redirect(url_for("profile"))
    else:
        error = None

    return render_expense_form(form, error)


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit_expense(id):
    expense = get_expense(id, session["user_id"])
    if expense is None:
        # Also covers other users' expenses, so ids can't be probed.
        abort(404)

    if request.method == "POST":
        form = request.form
        values, error = parse_expense_form(request.form)
        if error is None:
            update_expense(id, session["user_id"], **values)
            flash(f"Updated {values['description'] or values['category']}.")
            return redirect(url_for("profile"))
    else:
        form = {
            "amount": f"{expense['amount']:.2f}".removesuffix(".00"),
            "category": expense["category"],
            "date": expense["date"],
            "description": expense["description"],
        }
        error = None

    return render_expense_form(form, error, expense=expense)


def render_expense_form(form, error, expense=None):
    """Render the add form, or the edit form when an existing expense is given."""
    return render_template(
        "expense_form.html",
        form=form,
        error=error,
        expense=expense,
        categories=CATEGORIES,
        today=date.today().isoformat(),
        max_description=MAX_DESCRIPTION_LENGTH,
    ), 400 if error else 200


@app.route("/expenses/<int:id>/delete", methods=["GET", "POST"])
@login_required
def delete_expense(id):
    expense = get_expense(id, session["user_id"])
    if expense is None:
        abort(404)

    # GET only asks for confirmation; deleting needs the POST from that page,
    # so a prefetched or forged link can't remove anything.
    if request.method == "GET":
        return render_template("expense_delete.html", expense=expense)

    remove_expense(id, session["user_id"])
    flash(f"Deleted {expense['description'] or expense['category']} ({format_inr(expense['amount'])}).")
    return redirect(url_for("profile"))


if __name__ == "__main__":
    app.run(debug=True, port=5001)
