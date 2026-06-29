import os
import argparse
import getpass
from functools import wraps

from flask import Flask, abort, redirect, render_template, request, session, url_for

from cloud_auth.store import UserStore


DEFAULT_DATABASE = "/opt/zhishao-auth/zhishao_auth.db"


def create_admin_user(app, username, password):
    return app.config["USER_STORE"].create_user(username, password, role="admin")


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        DATABASE=os.environ.get("ZHISHAO_AUTH_DB", DEFAULT_DATABASE),
        SECRET_KEY=os.environ.get("ZHISHAO_AUTH_SECRET", "change-this-secret-before-production"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("ZHISHAO_AUTH_COOKIE_SECURE", "0").lower() in {"1", "true", "yes"},
    )
    if config:
        app.config.update(config)

    app.config["USER_STORE"] = UserStore(app.config["DATABASE"])

    def current_user():
        user_id = session.get("user_id")
        if not user_id:
            return None
        user = app.config["USER_STORE"].get_user(user_id)
        if not user or not user.get("enabled"):
            session.clear()
            return None
        return user

    def login_required(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                return redirect(url_for("login", next=request.path))
            return fn(user, *args, **kwargs)

        return wrapper

    def admin_required(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                return redirect(url_for("login", next=request.path))
            if user.get("role") != "admin":
                abort(403)
            return fn(user, *args, **kwargs)

        return wrapper

    @app.get("/")
    def index():
        return redirect(url_for("login"))

    @app.get("/login")
    def login_form():
        return render_template("login.html", error="", next_url=request.args.get("next", "/"))

    @app.post("/login")
    def login():
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        user = app.config["USER_STORE"].authenticate(username, password)
        if not user:
            return render_template(
                "login.html",
                error="用户名或密码错误。",
                next_url=request.form.get("next") or request.args.get("next") or "/",
            ), 401
        session.clear()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["role"] = user["role"]
        return redirect(request.form.get("next") or request.args.get("next") or "/")

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/auth/verify")
    def verify():
        return ("", 204) if current_user() else ("", 401)

    @app.get("/admin/users")
    @admin_required
    def admin_users(_user):
        users = app.config["USER_STORE"].list_users()
        return render_template("users.html", users=users, error="")

    @app.post("/admin/users")
    @admin_required
    def admin_create_user(_user):
        try:
            app.config["USER_STORE"].create_user(
                request.form.get("username", ""),
                request.form.get("password", ""),
                role=request.form.get("role", "user"),
            )
        except ValueError as exc:
            users = app.config["USER_STORE"].list_users()
            return render_template("users.html", users=users, error=str(exc)), 400
        return redirect(url_for("admin_users"))

    @app.post("/admin/users/<int:user_id>/password")
    @admin_required
    def admin_set_password(_user, user_id):
        try:
            app.config["USER_STORE"].set_password(user_id, request.form.get("password", ""))
        except ValueError as exc:
            return str(exc), 400
        return redirect(url_for("admin_users"))

    @app.post("/admin/users/<int:user_id>/toggle")
    @admin_required
    def admin_toggle_user(_user, user_id):
        store = app.config["USER_STORE"]
        target = store.get_user(user_id)
        if not target:
            return "用户不存在。", 404
        try:
            store.set_enabled(user_id, not bool(target.get("enabled")))
        except ValueError as exc:
            return str(exc), 400
        return redirect(url_for("admin_users"))

    @app.post("/admin/users/<int:user_id>/delete")
    @admin_required
    def admin_delete_user(_user, user_id):
        try:
            app.config["USER_STORE"].delete_user(user_id)
        except ValueError as exc:
            return str(exc), 400
        return redirect(url_for("admin_users"))

    app.current_user = current_user
    app.login_required = login_required
    app.admin_required = admin_required
    return app


def main(argv=None):
    parser = argparse.ArgumentParser(description="ZhiShao cloud authentication gateway")
    parser.add_argument("--db", default=os.environ.get("ZHISHAO_AUTH_DB", DEFAULT_DATABASE), help="SQLite database path")
    sub = parser.add_subparsers(dest="command")

    create_admin = sub.add_parser("create-admin", help="create an administrator account")
    create_admin.add_argument("username", help="administrator username")

    serve = sub.add_parser("serve", help="run the local Flask server")
    serve.add_argument("--host", default=os.environ.get("ZHISHAO_AUTH_HOST", "127.0.0.1"))
    serve.add_argument("--port", default=int(os.environ.get("ZHISHAO_AUTH_PORT", "9100")), type=int)

    args = parser.parse_args(argv)
    app = create_app({"DATABASE": args.db})

    if args.command == "create-admin":
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            raise SystemExit("两次密码不一致。")
        user = create_admin_user(app, args.username, password)
        print(f"管理员已创建：{user['username']}")
        return 0

    host = getattr(args, "host", os.environ.get("ZHISHAO_AUTH_HOST", "127.0.0.1"))
    port = getattr(args, "port", int(os.environ.get("ZHISHAO_AUTH_PORT", "9100")))
    app.run(host=host, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
