"""
database.py
SQLite schema creation + a single place to get a connection from.
"""

import sqlite3
import hashlib
from datetime import datetime

DB_PATH = "expenses.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password: str) -> str:
    salt = "expense_system_salt"
    return hashlib.sha256((salt + password).encode()).hexdigest()


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_setting(key, default=None):
    """Fetch a single setting value from the settings table (as a string)."""
    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    """Insert or update a setting value."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )
    conn.commit()
    conn.close()


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS departments (
            department_id INTEGER PRIMARY KEY AUTOINCREMENT,
            department_name TEXT UNIQUE NOT NULL
        );

               CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            department TEXT,
            role TEXT NOT NULL CHECK (role IN ('employee', 'manager', 'admin')),
            is_active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS expenses (
            expense_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT,
            department TEXT,
            date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending' CHECK (status IN ('Pending', 'Approved', 'Rejected')),
            flagged INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

               CREATE TABLE IF NOT EXISTS approvals (
            approval_id INTEGER PRIMARY KEY AUTOINCREMENT,
            expense_id INTEGER NOT NULL,
            manager_id INTEGER NOT NULL,
            decision TEXT NOT NULL CHECK (decision IN ('Approved', 'Rejected')),
            comment TEXT,
            date TEXT NOT NULL,
            FOREIGN KEY (expense_id) REFERENCES expenses(expense_id),
            FOREIGN KEY (manager_id) REFERENCES users(user_id)
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    conn.commit()

       # Migration: add is_active column if the DB was created before this feature existed
    existing_cols = [row["name"] for row in cur.execute("PRAGMA table_info(users)").fetchall()]
    if "is_active" not in existing_cols:
        cur.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        conn.commit()

    # Seed default settings if not already present
    cur.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
        ("unusual_expense_threshold", "50000"),
    )
    conn.commit()

    cur.execute("SELECT COUNT(*) AS c FROM departments")
    if cur.fetchone()["c"] == 0:
        depts = ["Logistics", "Marketing", "Finance", "IT", "Human Resources", "Operations"]
        cur.executemany("INSERT INTO departments (department_name) VALUES (?)", [(d,) for d in depts])
        conn.commit()

    cur.execute("SELECT COUNT(*) AS c FROM users")
    if cur.fetchone()["c"] == 0:
        seed_users = [
            ("System Admin", "admin@company.com", "admin123", "Finance", "admin"),
            ("Jane Manager", "manager@company.com", "manager123", "Logistics", "manager"),
            ("John Employee", "employee@company.com", "employee123", "Logistics", "employee"),
        ]
        for name, email, pw, dept, role in seed_users:
            cur.execute(
                "INSERT INTO users (name, email, password, department, role) VALUES (?, ?, ?, ?, ?)",
                (name, email, hash_password(pw), dept, role),
            )
        conn.commit()

    conn.close()
