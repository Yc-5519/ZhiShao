import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash


VALID_ROLES = {"admin", "user"}


class UserStore:
    """SQLite user store for the cloud authentication gateway."""

    def __init__(self, db_path):
        self.db_path = db_path
        parent = os.path.dirname(os.path.abspath(db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.lock = threading.RLock()
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _now(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _init_db(self):
        with self.lock, self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_login_at TEXT DEFAULT ''
                )
                """
            )

    def _row_to_dict(self, row):
        return dict(row) if row else None

    def _clean_username(self, username):
        username = str(username or "").strip()
        if not username:
            raise ValueError("用户名不能为空。")
        if len(username) > 64:
            raise ValueError("用户名不能超过 64 个字符。")
        return username

    def _clean_role(self, role):
        role = str(role or "user").strip()
        if role not in VALID_ROLES:
            raise ValueError("角色必须是 admin 或 user。")
        return role

    def create_user(self, username, password, role="user", enabled=True):
        username = self._clean_username(username)
        role = self._clean_role(role)
        if not str(password or ""):
            raise ValueError("密码不能为空。")
        now = self._now()
        password_hash = generate_password_hash(str(password))
        try:
            with self.lock, self._connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO users(username, password_hash, role, enabled, created_at, updated_at, last_login_at)
                    VALUES(?, ?, ?, ?, ?, ?, '')
                    """,
                    (username, password_hash, role, 1 if enabled else 0, now, now),
                )
                user_id = cursor.lastrowid
        except sqlite3.IntegrityError as exc:
            raise ValueError("用户名已存在。") from exc
        return self.get_user(user_id)

    def get_user(self, user_id):
        with self.lock, self._connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._row_to_dict(row)

    def get_user_by_username(self, username):
        username = str(username or "").strip()
        with self.lock, self._connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return self._row_to_dict(row)

    def list_users(self):
        with self.lock, self._connection() as conn:
            rows = conn.execute("SELECT * FROM users ORDER BY role ASC, username ASC").fetchall()
        return [dict(row) for row in rows]

    def authenticate(self, username, password):
        user = self.get_user_by_username(username)
        if not user or not user.get("enabled"):
            return None
        if not check_password_hash(user["password_hash"], str(password or "")):
            return None
        now = self._now()
        with self.lock, self._connection() as conn:
            conn.execute(
                "UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?",
                (now, now, user["id"]),
            )
        return self.get_user(user["id"])

    def set_password(self, user_id, password):
        if not str(password or ""):
            raise ValueError("密码不能为空。")
        password_hash = generate_password_hash(str(password))
        now = self._now()
        with self.lock, self._connection() as conn:
            cursor = conn.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (password_hash, now, user_id),
            )
        if cursor.rowcount == 0:
            raise ValueError("用户不存在。")
        return self.get_user(user_id)

    def set_enabled(self, user_id, enabled):
        user = self.get_user(user_id)
        if not user:
            raise ValueError("用户不存在。")
        if user["role"] == "admin" and not enabled and self.admin_count() <= 1:
            raise ValueError("不能禁用最后一个管理员。")
        now = self._now()
        with self.lock, self._connection() as conn:
            conn.execute(
                "UPDATE users SET enabled = ?, updated_at = ? WHERE id = ?",
                (1 if enabled else 0, now, user_id),
            )
        return self.get_user(user_id)

    def delete_user(self, user_id):
        user = self.get_user(user_id)
        if not user:
            return
        if user["role"] == "admin" and self.admin_count() <= 1:
            raise ValueError("不能删除最后一个管理员。")
        with self.lock, self._connection() as conn:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    def admin_count(self):
        with self.lock, self._connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM users WHERE role = 'admin'").fetchone()
        return int(row["c"] if row else 0)
