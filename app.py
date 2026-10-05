"""
app.py
Flask web app for the AI-Powered Organisational Expense Management System.

Run with:  python app.py
Then open: http://127.0.0.1:5000

Seeded logins (created on first run):
  Admin:    admin@company.com    / admin123
  Manager:  manager@company.com  / manager123
  Employee: employee@company.com / employee123
"""

from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash

from database import get_connection, init_db, hash_password, now_str, get_setting, set_setting
from categorizer import categorize, is_unusual_expense

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-in-production"


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def login_required(role=None):
    """Decorator factory. role can be a string or a tuple of allowed roles."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in first.", "error")
                return redirect(url_for("login"))

            conn = get_connection()
            live_user = conn.execute(
                "SELECT is_active FROM users WHERE user_id = ?", (session["user_id"],)
            ).fetchone()
            conn.close()
            if live_user is None or not live_user["is_active"]:
                session.clear()
                flash("This account has been deactivated. Contact your administrator.", "error")
                return redirect(url_for("login"))

            if role is not None:
                allowed = (role,) if isinstance(role, str) else role
                if session.get("role") not in allowed:
                    flash("You don't have permission to view that page.", "error")
                    return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return wrapped
    return decorator


def current_user():
    if "user_id" not in session:
        return None
    return {
        "user_id": session["user_id"],
        "name": session["name"],
        "role": session["role"],
        "department": session["department"],
    }


@app.context_processor
def inject_user():
    return {"current_user": current_user()}


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_connection()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        if user is None or user["password"] != hash_password(password):
            flash("Invalid email or password.", "error")
            return redirect(url_for("login"))

        if not user["is_active"]:
            flash("This account has been deactivated. Contact your administrator.", "error")
            return redirect(url_for("login"))

        session["user_id"] = user["user_id"]
        session["name"] = user["name"]
        session["role"] = user["role"]
        session["department"] = user["department"]
        flash(f"Welcome back, {user['name']}!", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Self-registration is limited to the 'employee' role -- managers and
    admins are provisioned by an existing admin (see /admin/users)."""
    conn = get_connection()
    departments = conn.execute("SELECT department_name FROM departments ORDER BY department_name").fetchall()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        department = request.form.get("department", "")

        if not name or not email or not password or not department:
            flash("All fields are required.", "error")
            conn.close()
            return redirect(url_for("register"))

        existing = conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            flash("An account with that email already exists.", "error")
            conn.close()
            return redirect(url_for("register"))

        conn.execute(
            "INSERT INTO users (name, email, password, department, role) VALUES (?, ?, ?, ?, 'employee')",
            (name, email, hash_password(password), department),
        )
        conn.commit()
        conn.close()
        flash("Account created. You can now log in.", "success")
        return redirect(url_for("login"))

    conn.close()
    return render_template("register.html", departments=departments)


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Dashboard (role-aware landing page)
# ---------------------------------------------------------------------------

@app.route("/dashboard")
@login_required()
def dashboard():
    user = current_user()
    conn = get_connection()

    if user["role"] == "admin":
        totals = conn.execute(
            """
            SELECT
                COALESCE(SUM(amount), 0) AS total,
                COALESCE(SUM(CASE WHEN status = 'Pending' THEN amount ELSE 0 END), 0) AS pending,
                COALESCE(SUM(CASE WHEN status = 'Approved' THEN amount ELSE 0 END), 0) AS approved,
                COALESCE(SUM(CASE WHEN status = 'Rejected' THEN amount ELSE 0 END), 0) AS rejected
            FROM expenses
            """
        ).fetchone()
        by_department = conn.execute(
            """
            SELECT department, COALESCE(SUM(amount), 0) AS total
            FROM expenses
            GROUP BY department
            ORDER BY total DESC
            """
        ).fetchall()
        flagged = conn.execute(
            "SELECT COUNT(*) AS c FROM expenses WHERE flagged = 1 AND status = 'Pending'"
        ).fetchone()["c"]
        conn.close()
        return render_template(
            "dashboard_admin.html", totals=totals, by_department=by_department, flagged=flagged
        )

    elif user["role"] == "manager":
        totals = conn.execute(
            """
            SELECT
                COALESCE(SUM(amount), 0) AS total,
                COALESCE(SUM(CASE WHEN status = 'Pending' THEN amount ELSE 0 END), 0) AS pending,
                COALESCE(SUM(CASE WHEN status = 'Approved' THEN amount ELSE 0 END), 0) AS approved,
                COALESCE(SUM(CASE WHEN status = 'Rejected' THEN amount ELSE 0 END), 0) AS rejected
            FROM expenses WHERE department = ?
            """,
            (user["department"],),
        ).fetchone()
        pending_count = conn.execute(
            "SELECT COUNT(*) AS c FROM expenses WHERE department = ? AND status = 'Pending'",
            (user["department"],),
        ).fetchone()["c"]
        conn.close()
        return render_template("dashboard_manager.html", totals=totals, pending_count=pending_count)

    else:  # employee
        my_expenses = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? ORDER BY date DESC LIMIT 5",
            (user["user_id"],),
        ).fetchall()
        totals = conn.execute(
            """
            SELECT
                COALESCE(SUM(amount), 0) AS total,
                COALESCE(SUM(CASE WHEN status = 'Pending' THEN amount ELSE 0 END), 0) AS pending,
                COALESCE(SUM(CASE WHEN status = 'Approved' THEN amount ELSE 0 END), 0) AS approved
            FROM expenses WHERE user_id = ?
            """,
            (user["user_id"],),
        ).fetchone()
        conn.close()
        return render_template("dashboard_employee.html", my_expenses=my_expenses, totals=totals)


# ---------------------------------------------------------------------------
# Employee: submit + view own expenses
# ---------------------------------------------------------------------------

@app.route("/expenses/new", methods=["GET", "POST"])
@login_required(("employee", "manager", "admin"))
def new_expense():
    user = current_user()

    if request.method == "POST":
        description = request.form.get("description", "").strip()
        amount_raw = request.form.get("amount", "").strip()

        if not description or not amount_raw:
            flash("Description and amount are required.", "error")
            return redirect(url_for("new_expense"))

        try:
            amount = float(amount_raw)
            if amount <= 0:
                raise ValueError
        except ValueError:
            flash("Amount must be a positive number.", "error")
            return redirect(url_for("new_expense"))

        category = categorize(description)

        conn = get_connection()
        past_amounts = [
            row["amount"]
            for row in conn.execute(
                "SELECT amount FROM expenses WHERE user_id = ?", (user["user_id"],)
            ).fetchall()
        ]
        threshold = float(get_setting("unusual_expense_threshold", 50000))
        flagged, reason = is_unusual_expense(amount, past_amounts, flat_threshold=threshold)

        conn.execute(
            """
            INSERT INTO expenses (user_id, description, amount, category, department, date, status, flagged)
            VALUES (?, ?, ?, ?, ?, ?, 'Pending', ?)
            """,
            (user["user_id"], description, amount, category, user["department"], now_str(), int(flagged)),
        )
        conn.commit()
        conn.close()

        flash(f"Expense submitted. AI categorized it as '{category}'.", "success")
        if flagged:
            flash(f"⚠ Unusual expense detected: {reason}", "warning")
        return redirect(url_for("my_expenses"))

    return render_template("new_expense.html")


@app.route("/expenses/mine")
@login_required(("employee", "manager", "admin"))
def my_expenses():
    user = current_user()
    conn = get_connection()
    expenses = conn.execute(
        "SELECT * FROM expenses WHERE user_id = ? ORDER BY date DESC", (user["user_id"],)
    ).fetchall()
    conn.close()
    return render_template("my_expenses.html", expenses=expenses)


# ---------------------------------------------------------------------------
# Manager / Admin: review expenses
# ---------------------------------------------------------------------------

@app.route("/expenses/review")
@login_required(("manager", "admin"))
def review_expenses():
    user = current_user()
    conn = get_connection()

    status_filter = request.args.get("status", "Pending")
    valid_statuses = ("Pending", "Approved", "Rejected", "All")
    if status_filter not in valid_statuses:
        status_filter = "Pending"

    query = """
        SELECT e.*, u.name AS employee_name
        FROM expenses e JOIN users u ON e.user_id = u.user_id
    """
    params = []
    conditions = []

    if user["role"] == "manager":
        conditions.append("e.department = ?")
        params.append(user["department"])

    if status_filter != "All":
        conditions.append("e.status = ?")
        params.append(status_filter)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY e.flagged DESC, e.date DESC"

    expenses = conn.execute(query, params).fetchall()
    conn.close()
    return render_template("review_expenses.html", expenses=expenses, status_filter=status_filter)


@app.route("/expenses/<int:expense_id>/decide", methods=["POST"])
@login_required(("manager", "admin"))
def decide_expense(expense_id):
    user = current_user()
    decision = request.form.get("decision")
    comment = request.form.get("comment", "").strip()

    if decision not in ("Approved", "Rejected"):
        flash("Invalid decision.", "error")
        return redirect(url_for("review_expenses"))

    conn = get_connection()
    expense = conn.execute("SELECT * FROM expenses WHERE expense_id = ?", (expense_id,)).fetchone()

    if expense is None:
        flash("Expense not found.", "error")
        conn.close()
        return redirect(url_for("review_expenses"))

    if user["role"] == "manager" and expense["department"] != user["department"]:
        flash("You can only review expenses from your own department.", "error")
        conn.close()
        return redirect(url_for("review_expenses"))

    conn.execute("UPDATE expenses SET status = ? WHERE expense_id = ?", (decision, expense_id))
    conn.execute(
        "INSERT INTO approvals (expense_id, manager_id, decision, comment, date) VALUES (?, ?, ?, ?, ?)",
        (expense_id, user["user_id"], decision, comment, now_str()),
    )
    conn.commit()
    conn.close()

    flash(f"Expense {decision.lower()}.", "success")
    return redirect(url_for("review_expenses"))


# ---------------------------------------------------------------------------
# Admin: reports, departments, users
# ---------------------------------------------------------------------------

@app.route("/admin/reports")
@login_required("admin")
def reports():
    conn = get_connection()

    by_category = conn.execute(
        """
        SELECT category, COUNT(*) AS count, COALESCE(SUM(amount), 0) AS total
        FROM expenses GROUP BY category ORDER BY total DESC
        """
    ).fetchall()

    by_department = conn.execute(
        """
        SELECT department, COUNT(*) AS count, COALESCE(SUM(amount), 0) AS total
        FROM expenses GROUP BY department ORDER BY total DESC
        """
    ).fetchall()

    by_month = conn.execute(
        """
        SELECT strftime('%Y-%m', date) AS month, COALESCE(SUM(amount), 0) AS total
        FROM expenses GROUP BY month ORDER BY month
        """
    ).fetchall()

    flagged_expenses = conn.execute(
        """
        SELECT e.*, u.name AS employee_name
        FROM expenses e JOIN users u ON e.user_id = u.user_id
        WHERE e.flagged = 1
        ORDER BY e.date DESC
        """
    ).fetchall()

    conn.close()
    return render_template(
        "reports.html",
        by_category=by_category,
        by_department=by_department,
        by_month=by_month,
        flagged_expenses=flagged_expenses,
    )


@app.route("/admin/users", methods=["GET", "POST"])
@login_required("admin")
def manage_users():
    conn = get_connection()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        department = request.form.get("department", "")
        role = request.form.get("role", "employee")

        if role not in ("employee", "manager", "admin"):
            role = "employee"

        if not name or not email or not password or not department:
            flash("All fields are required.", "error")
        else:
            existing = conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
            if existing:
                flash("A user with that email already exists.", "error")
            else:
                conn.execute(
                    "INSERT INTO users (name, email, password, department, role) VALUES (?, ?, ?, ?, ?)",
                    (name, email, hash_password(password), department, role),
                )
                conn.commit()
                flash(f"User '{name}' created as {role}.", "success")

    users = conn.execute("SELECT * FROM users ORDER BY role, name").fetchall()
    departments = conn.execute("SELECT department_name FROM departments ORDER BY department_name").fetchall()
    conn.close()
    return render_template("manage_users.html", users=users, departments=departments)


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@login_required("admin")
def delete_user(user_id):
    current = current_user()

    if user_id == current["user_id"]:
        flash("You cannot delete your own account while logged in as it.", "error")
        return redirect(url_for("manage_users"))

    conn = get_connection()
    target = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

    if target is None:
        flash("User not found.", "error")
        conn.close()
        return redirect(url_for("manage_users"))

    expense_count = conn.execute(
        "SELECT COUNT(*) AS c FROM expenses WHERE user_id = ?", (user_id,)
    ).fetchone()["c"]
    approval_count = conn.execute(
        "SELECT COUNT(*) AS c FROM approvals WHERE manager_id = ?", (user_id,)
    ).fetchone()["c"]

    if expense_count > 0 or approval_count > 0:
        flash(
            f"Cannot delete '{target['name']}': they have {expense_count} expense(s) and "
            f"{approval_count} approval decision(s) on record. Deactivate the account instead "
            "of deleting it, to preserve the audit trail.",
            "error",
        )
        conn.close()
        return redirect(url_for("manage_users"))
    
    conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

    flash(f"User '{target['name']}' deleted.", "success")
    return redirect(url_for("manage_users"))

@app.route("/admin/users/<int:user_id>/toggle-active", methods=["POST"])
@login_required("admin")
def admin_toggle_active(user_id):
    """Admin can activate/deactivate any account, from any department."""
    current = current_user()

    if user_id == current["user_id"]:
        flash("You cannot deactivate your own account while logged in as it.", "error")
        return redirect(url_for("manage_users"))

    conn = get_connection()
    target = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

    if target is None:
        flash("User not found.", "error")
        conn.close()
        return redirect(url_for("manage_users"))

    new_status = 0 if target["is_active"] else 1
    conn.execute("UPDATE users SET is_active = ? WHERE user_id = ?", (new_status, user_id))
    conn.commit()
    conn.close()

    action = "reactivated" if new_status else "deactivated"
    flash(f"User '{target['name']}' {action}.", "success")
    return redirect(url_for("manage_users"))


@app.route("/manager/team")
@login_required("manager")
def manage_team():
    """Manager view: employees in their own department only, with deactivate control."""
    user = current_user()
    conn = get_connection()
    team = conn.execute(
        """
        SELECT * FROM users
        WHERE department = ? AND role = 'employee'
        ORDER BY name
        """,
        (user["department"],),
    ).fetchall()
    conn.close()
    return render_template("manage_team.html", team=team)


@app.route("/manager/team/<int:user_id>/toggle-active", methods=["POST"])
@login_required("manager")
def manager_toggle_active(user_id):
    """Manager can only deactivate/reactivate employees within their own department."""
    user = current_user()
    conn = get_connection()
    target = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

    if target is None:
        flash("User not found.", "error")
        conn.close()
        return redirect(url_for("manage_team"))

    if target["department"] != user["department"] or target["role"] != "employee":
        flash("You can only manage employees within your own department.", "error")
        conn.close()
        return redirect(url_for("manage_team"))

    new_status = 0 if target["is_active"] else 1
    conn.execute("UPDATE users SET is_active = ? WHERE user_id = ?", (new_status, user_id))
    conn.commit()
    conn.close()

    action = "reactivated" if new_status else "deactivated"
    flash(f"'{target['name']}' {action}.", "success")
    return redirect(url_for("manage_team"))

    
@app.route("/admin/departments", methods=["GET", "POST"])
@login_required("admin")
def manage_departments():
    conn = get_connection()

    if request.method == "POST":
        name = request.form.get("department_name", "").strip()
        if name:
            try:
                conn.execute("INSERT INTO departments (department_name) VALUES (?)", (name,))
                conn.commit()
                flash(f"Department '{name}' added.", "success")
            except Exception:
                flash("That department already exists.", "error")

    departments = conn.execute(
        """
        SELECT d.department_name,
               COALESCE(SUM(e.amount), 0) AS total_spent,
               COUNT(e.expense_id) AS expense_count
        FROM departments d
        LEFT JOIN expenses e ON e.department = d.department_name
        GROUP BY d.department_name
        ORDER BY d.department_name
        """
    ).fetchall()
    conn.close()
    return render_template("manage_departments.html", departments=departments)
@app.route("/admin/settings", methods=["GET", "POST"])
@login_required("admin")
def manage_settings():
    if request.method == "POST":
        threshold_raw = request.form.get("unusual_expense_threshold", "").strip()
        try:
            threshold = float(threshold_raw)
            if threshold <= 0:
                raise ValueError
            set_setting("unusual_expense_threshold", threshold)
            flash(f"Unusual expense threshold updated to ₦{threshold:,.2f}.", "success")
        except ValueError:
            flash("Threshold must be a positive number.", "error")
        return redirect(url_for("manage_settings"))

    current_threshold = get_setting("unusual_expense_threshold", 50000)
    return render_template("manage_settings.html", current_threshold=float(current_threshold))


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="127.0.0.1", port=5000)
