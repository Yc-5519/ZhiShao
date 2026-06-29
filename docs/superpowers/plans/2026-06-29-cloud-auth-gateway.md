# Cloud Auth Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a cloud-hosted authentication gateway for the public ZhiShao monitor page, with admin-managed users stored on the cloud server.

**Architecture:** Add a separate `cloud_auth/` Flask service that owns login, logout, signed sessions, user management, and the Nginx `auth_request` verify endpoint. The service stores users in a cloud SQLite database and proxies no business logic itself; Nginx keeps forwarding authenticated monitor traffic to the existing RDK upstream. RDK code remains unchanged for this feature.

**Tech Stack:** Python 3, Flask, SQLite, Werkzeug password hashing, unittest, systemd, Nginx `auth_request`.

---

## File Structure

- Create `cloud_auth/app.py`: Flask application factory, routes, CLI admin creation, and entrypoint.
- Create `cloud_auth/store.py`: SQLite user store with password hash operations and admin-safety checks.
- Create `cloud_auth/templates/login.html`: login page.
- Create `cloud_auth/templates/users.html`: admin user management page.
- Create `cloud_auth/requirements.txt`: cloud auth runtime dependencies.
- Create `cloud_auth/README.md`: deployment and operation commands.
- Create `cloud_auth/deploy/zhishao-auth.service`: systemd unit template.
- Create `cloud_auth/deploy/nginx-auth-gateway.conf.example`: Nginx example that preserves the existing RDK upstream.
- Create `cloud_auth/tests/test_auth_gateway.py`: unit tests for auth, roles, user CRUD, and verify route.
- Modify `.gitignore`: ensure cloud auth runtime database and local venv files are excluded.
- Modify `README.md`: mention `cloud_auth/` as the cloud login gateway.

### Task 1: User Store

**Files:**
- Create: `cloud_auth/store.py`
- Test: `cloud_auth/tests/test_auth_gateway.py`

- [ ] **Step 1: Write failing store tests**

Add tests covering user creation, password checking, duplicate usernames, disabled login rejection, and preventing deletion of the last admin.

Run: `python -m unittest cloud_auth.tests.test_auth_gateway`
Expected: FAIL because `cloud_auth.store` does not exist.

- [ ] **Step 2: Implement `UserStore`**

Implement SQLite schema, `create_user`, `authenticate`, `list_users`, `set_enabled`, `set_password`, `delete_user`, and `admin_count`. Store password hashes using Werkzeug, never plaintext.

- [ ] **Step 3: Run store tests**

Run: `python -m unittest cloud_auth.tests.test_auth_gateway`
Expected: store tests PASS.

### Task 2: Flask Auth App

**Files:**
- Create: `cloud_auth/app.py`
- Create: `cloud_auth/templates/login.html`
- Test: `cloud_auth/tests/test_auth_gateway.py`

- [ ] **Step 1: Write failing route tests**

Add tests for `/login`, `/logout`, `/auth/verify`, disabled user login failure, and admin/user session behavior.

Run: `python -m unittest cloud_auth.tests.test_auth_gateway`
Expected: FAIL because Flask routes do not exist.

- [ ] **Step 2: Implement routes**

Implement `create_app`, login form handling, logout, session setup, `login_required`, `admin_required`, and `/auth/verify` returning 204 when authenticated and 401 otherwise.

- [ ] **Step 3: Run route tests**

Run: `python -m unittest cloud_auth.tests.test_auth_gateway`
Expected: auth route tests PASS.

### Task 3: Admin User Management

**Files:**
- Modify: `cloud_auth/app.py`
- Create: `cloud_auth/templates/users.html`
- Test: `cloud_auth/tests/test_auth_gateway.py`

- [ ] **Step 1: Write failing admin CRUD tests**

Add tests that admin can create users, change passwords, disable/enable users, delete normal users, and normal users cannot open `/admin/users`.

Run: `python -m unittest cloud_auth.tests.test_auth_gateway`
Expected: FAIL because admin routes do not exist.

- [ ] **Step 2: Implement admin routes and template**

Implement `/admin/users`, `/admin/users/<id>/password`, `/admin/users/<id>/toggle`, and `/admin/users/<id>/delete` using POST for writes. Reject deletion of the last admin.

- [ ] **Step 3: Run admin tests**

Run: `python -m unittest cloud_auth.tests.test_auth_gateway`
Expected: admin CRUD tests PASS.

### Task 4: CLI, Deployment Files, and Docs

**Files:**
- Modify: `cloud_auth/app.py`
- Create: `cloud_auth/requirements.txt`
- Create: `cloud_auth/README.md`
- Create: `cloud_auth/deploy/zhishao-auth.service`
- Create: `cloud_auth/deploy/nginx-auth-gateway.conf.example`
- Modify: `README.md`
- Modify: `.gitignore`

- [ ] **Step 1: Add CLI test**

Add a small test that `create_app` can initialize with a temp database and that CLI helper logic can create an admin through the store without plaintext password storage.

Run: `python -m unittest cloud_auth.tests.test_auth_gateway`
Expected: FAIL until CLI helper is exposed.

- [ ] **Step 2: Implement CLI and deployment docs**

Add `create-admin <username>` command using `getpass`, requirements, README deployment steps, systemd unit template, and Nginx example using `/auth/verify`.

- [ ] **Step 3: Run full verification**

Run: `python -m unittest cloud_auth.tests.test_auth_gateway`
Expected: all cloud auth tests PASS.

Run: Python AST parse over `cloud_auth/`.
Expected: `failed=0`.

### Task 5: Cloud Server Sync Preparation

**Files:**
- No source change required.

- [ ] **Step 1: Check Git scope**

Run: `git status --short`
Expected: changes include only `cloud_auth/`, `.gitignore`, `README.md`, and the implementation plan, plus pre-existing RDK working tree changes that remain unstaged unless explicitly requested.

- [ ] **Step 2: Package cloud auth only**

Create a tar archive from `cloud_auth/`, excluding `*.db`, `.env`, `__pycache__`, and venv directories.

- [ ] **Step 3: Upload to cloud server**

Upload to `ubuntu@124.222.118.121:/tmp/zhishao-auth.tar` through the available SSH path. Do not edit Nginx live config until the service passes local cloud-side tests.

- [ ] **Step 4: Cloud-side dry run**

On the cloud server, extract to `/home/ubuntu/zhishao_auth_test`, create a venv, install requirements, run unit tests, and start on localhost test port only.

---

## Self-Review

- Spec coverage: The plan covers cloud-side account storage, admin-created users only, login/logout, user CRUD, password hashes, Nginx verify route, deployment docs, and tests.
- Placeholder scan: No TODO/TBD placeholders remain. The Nginx upstream must be read from current cloud config before live deployment, as documented in the design.
- Type consistency: The plan consistently uses `UserStore`, `create_app`, Flask sessions, SQLite users, and `/auth/verify`.
