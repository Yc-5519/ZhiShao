import os
import tempfile
import unittest

from cloud_auth.store import UserStore
from cloud_auth.app import create_admin_user, create_app


class UserStoreTests(unittest.TestCase):
    def make_store(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        return UserStore(os.path.join(self.tmp.name, "auth.db"))

    def test_create_user_stores_hash_not_plaintext(self):
        store = self.make_store()
        user = store.create_user("admin", "secret123", role="admin")

        self.assertEqual(user["username"], "admin")
        self.assertEqual(user["role"], "admin")
        self.assertNotEqual(user["password_hash"], "secret123")
        self.assertTrue(user["password_hash"].startswith(("scrypt:", "pbkdf2:")))

    def test_authenticate_accepts_password_and_updates_last_login(self):
        store = self.make_store()
        store.create_user("care", "safe-password", role="user")

        user = store.authenticate("care", "safe-password")

        self.assertIsNotNone(user)
        self.assertEqual(user["username"], "care")
        self.assertTrue(user["last_login_at"])
        self.assertIsNone(store.authenticate("care", "wrong-password"))

    def test_duplicate_username_is_rejected(self):
        store = self.make_store()
        store.create_user("care", "password-a", role="user")

        with self.assertRaises(ValueError):
            store.create_user("care", "password-b", role="user")

    def test_disabled_user_cannot_login(self):
        store = self.make_store()
        user = store.create_user("care", "safe-password", role="user")
        store.set_enabled(user["id"], False)

        self.assertIsNone(store.authenticate("care", "safe-password"))
        disabled = store.get_user(user["id"])
        self.assertEqual(disabled["enabled"], 0)

    def test_password_can_be_changed(self):
        store = self.make_store()
        user = store.create_user("care", "old-password", role="user")
        store.set_password(user["id"], "new-password")

        self.assertIsNone(store.authenticate("care", "old-password"))
        self.assertIsNotNone(store.authenticate("care", "new-password"))

    def test_cannot_delete_last_admin(self):
        store = self.make_store()
        admin = store.create_user("admin", "secret123", role="admin")

        with self.assertRaises(ValueError):
            store.delete_user(admin["id"])

        self.assertEqual(store.admin_count(), 1)

    def test_can_delete_normal_user(self):
        store = self.make_store()
        store.create_user("admin", "secret123", role="admin")
        user = store.create_user("care", "safe-password", role="user")

        store.delete_user(user["id"])

        self.assertIsNone(store.get_user(user["id"]))
        self.assertEqual([row["username"] for row in store.list_users()], ["admin"])


class AuthRouteTests(unittest.TestCase):
    def make_app(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        db_path = os.path.join(self.tmp.name, "auth.db")
        app = create_app({"TESTING": True, "DATABASE": db_path, "SECRET_KEY": "test-secret"})
        store = app.config["USER_STORE"]
        store.create_user("admin", "admin-pass", role="admin")
        store.create_user("care", "care-pass", role="user")
        return app, store

    def test_verify_requires_login_then_accepts_session(self):
        app, _store = self.make_app()
        client = app.test_client()

        self.assertEqual(client.get("/auth/verify").status_code, 401)

        response = client.post("/login", data={"username": "care", "password": "care-pass"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(client.get("/auth/verify").status_code, 204)

    def test_login_rejects_bad_password(self):
        app, _store = self.make_app()
        client = app.test_client()

        response = client.post("/login", data={"username": "care", "password": "wrong-pass"})

        self.assertEqual(response.status_code, 401)
        self.assertIn("用户名或密码错误".encode("utf-8"), response.data)
        self.assertEqual(client.get("/auth/verify").status_code, 401)

    def test_disabled_user_login_fails(self):
        app, store = self.make_app()
        user = store.get_user_by_username("care")
        store.set_enabled(user["id"], False)
        client = app.test_client()

        response = client.post("/login", data={"username": "care", "password": "care-pass"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(client.get("/auth/verify").status_code, 401)

    def test_logout_clears_session(self):
        app, _store = self.make_app()
        client = app.test_client()
        client.post("/login", data={"username": "care", "password": "care-pass"})
        self.assertEqual(client.get("/auth/verify").status_code, 204)

        response = client.post("/logout")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(client.get("/auth/verify").status_code, 401)


class AdminUserRouteTests(unittest.TestCase):
    def make_app(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        db_path = os.path.join(self.tmp.name, "auth.db")
        app = create_app({"TESTING": True, "DATABASE": db_path, "SECRET_KEY": "test-secret"})
        store = app.config["USER_STORE"]
        store.create_user("admin", "admin-pass", role="admin")
        store.create_user("care", "care-pass", role="user")
        return app, store

    def login(self, client, username, password):
        return client.post("/login", data={"username": username, "password": password})

    def test_admin_can_open_user_management_page(self):
        app, _store = self.make_app()
        client = app.test_client()
        self.login(client, "admin", "admin-pass")

        response = client.get("/admin/users")

        self.assertEqual(response.status_code, 200)
        self.assertIn("用户管理".encode("utf-8"), response.data)
        self.assertIn("care".encode("utf-8"), response.data)

    def test_normal_user_cannot_open_user_management_page(self):
        app, _store = self.make_app()
        client = app.test_client()
        self.login(client, "care", "care-pass")

        response = client.get("/admin/users")

        self.assertEqual(response.status_code, 403)

    def test_admin_can_create_user(self):
        app, store = self.make_app()
        client = app.test_client()
        self.login(client, "admin", "admin-pass")

        response = client.post("/admin/users", data={"username": "family", "password": "family-pass", "role": "user"})

        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(store.authenticate("family", "family-pass"))

    def test_admin_can_change_password(self):
        app, store = self.make_app()
        client = app.test_client()
        self.login(client, "admin", "admin-pass")
        user = store.get_user_by_username("care")

        response = client.post(f"/admin/users/{user['id']}/password", data={"password": "new-care-pass"})

        self.assertEqual(response.status_code, 302)
        self.assertIsNone(store.authenticate("care", "care-pass"))
        self.assertIsNotNone(store.authenticate("care", "new-care-pass"))

    def test_admin_can_disable_and_enable_user(self):
        app, store = self.make_app()
        client = app.test_client()
        self.login(client, "admin", "admin-pass")
        user = store.get_user_by_username("care")

        disabled = client.post(f"/admin/users/{user['id']}/toggle")
        self.assertEqual(disabled.status_code, 302)
        self.assertIsNone(store.authenticate("care", "care-pass"))

        enabled = client.post(f"/admin/users/{user['id']}/toggle")
        self.assertEqual(enabled.status_code, 302)
        self.assertIsNotNone(store.authenticate("care", "care-pass"))

    def test_admin_can_delete_normal_user(self):
        app, store = self.make_app()
        client = app.test_client()
        self.login(client, "admin", "admin-pass")
        user = store.get_user_by_username("care")

        response = client.post(f"/admin/users/{user['id']}/delete")

        self.assertEqual(response.status_code, 302)
        self.assertIsNone(store.get_user(user["id"]))

    def test_admin_cannot_delete_last_admin_from_route(self):
        app, store = self.make_app()
        client = app.test_client()
        self.login(client, "admin", "admin-pass")
        admin = store.get_user_by_username("admin")

        response = client.post(f"/admin/users/{admin['id']}/delete")

        self.assertEqual(response.status_code, 400)
        self.assertIsNotNone(store.get_user(admin["id"]))


class CliHelperTests(unittest.TestCase):
    def test_create_admin_user_helper(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_path = os.path.join(tmp, "auth.db")
            app = create_app({"TESTING": True, "DATABASE": db_path, "SECRET_KEY": "test-secret"})
            user = create_admin_user(app, "owner", "owner-pass")
            store = app.config["USER_STORE"]

            self.assertEqual(user["username"], "owner")
            self.assertEqual(user["role"], "admin")
            self.assertNotEqual(user["password_hash"], "owner-pass")
            self.assertIsNotNone(store.authenticate("owner", "owner-pass"))


if __name__ == "__main__":
    unittest.main()
