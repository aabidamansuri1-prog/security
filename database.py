"""SQLite storage for registered users and security alerts."""
import sqlite3
from datetime import datetime
import config


def _conn():
    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS alerts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            image_path TEXT)""")


def add_user(name):
    with _conn() as c:
        cur = c.execute("INSERT INTO users(name, created_at) VALUES(?,?)",
                        (name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        return cur.lastrowid


def get_user_by_name(name):
    with _conn() as c:
        return c.execute("SELECT * FROM users WHERE name=? COLLATE NOCASE", (name,)).fetchone()


def get_user(uid):
    with _conn() as c:
        return c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


def list_users():
    with _conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM users ORDER BY id")]


def delete_user(uid):
    with _conn() as c:
        c.execute("DELETE FROM users WHERE id=?", (uid,))


def add_alert(alert_type, image_path):
    now = datetime.now()
    with _conn() as c:
        cur = c.execute("INSERT INTO alerts(alert_type,date,time,image_path) VALUES(?,?,?,?)",
                        (alert_type, now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), image_path))
        return cur.lastrowid


def list_alerts(limit=100):
    with _conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,))]


def clear_alerts():
    with _conn() as c:
        c.execute("DELETE FROM alerts")
