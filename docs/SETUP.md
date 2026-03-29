# PyAdminer setup guide

This document walks through getting PyAdminer running locally. For feature overview and a full environment-variable reference, see the [README](../README.md) in the repository root.

## What you need

- **Git** and either **Docker** (recommended for a one-command stack) or **Python 3.9+** with a virtual environment.
- A **MySQL** or **MariaDB** server the app can reach (the Docker path below includes MySQL for you).

If you install the app on the host with `pip`, you also need **build tooling for `mysqlclient`** (C extension):

| OS | Typical packages / notes |
|----|---------------------------|
| Debian / Ubuntu | `default-libmysqlclient-dev`, `pkg-config`, `build-essential` |
| Fedora / RHEL | `mariadb-devel` or `mysql-devel`, `gcc`, `pkg-config` |
| macOS (Homebrew) | `brew install mysql-client pkg-config`; you may need `export PKG_CONFIG_PATH="$(brew --prefix mysql-client)/lib/pkgconfig"` before `pip install` |

---

## Option A: Docker (app + MySQL)

Best when you want the UI and a database without installing MySQL on your machine.

1. **Clone and enter the repo**

   ```bash
   git clone https://github.com/anilpokhariyal/py-adminer.git
   cd py-adminer
   ```

2. **Start the stack** (from the repo root)

   ```bash
   make docker-local
   ```

   Equivalent:

   ```bash
   docker compose -f docker/docker-compose.local.yml up --build -d
   ```

3. **Open the app**

   - UI: [http://127.0.0.1:8080](http://127.0.0.1:8080)
   - MySQL from your host (e.g. GUI client): host `127.0.0.1`, port **3307**, user `root`, password `root`, database `demo` (created by compose).

4. **Log in through the web UI** (connect PyAdminer to the *container* network)

   Because the browser talks to Flask, but Flask connects to MySQL *inside* Docker Compose, use the **service hostname** `mysql` as the server:

   | Field | Value |
   |-------|--------|
   | Server | `mysql` |
   | User | `root` |
   | Password | `root` |
   | Database | `demo` (optional) |

   The compose file sets `PYADMINER_DEFAULT_MYSQL_HOST=mysql` so the server field may already be prefilled.

5. **Live code changes**

   The project directory is bind-mounted at `/app` and `FLASK_DEBUG=1` is enabled, so edits to Python, templates, and static files usually reload without rebuilding.

6. **When to rebuild the image**

   Re-run `make docker-local` (or `docker compose ... up --build -d`) after changing **`docker/Dockerfile`** or **`requirements.txt`**.

7. **Useful commands**

   ```bash
   make docker-local-down      # stop and remove containers (volume kept)
   make docker-local-logs      # follow py-adminer logs
   make docker-local-restart   # restart only the app container
   ```

8. **Optional: custom `SECRET_KEY` for Docker**

   ```bash
   SECRET_KEY='your-long-random-string' make docker-local
   ```

---

## Optional: Marketing site in Docker (`pyadminer-web/`)

If you keep the static landing site under `pyadminer-web/` at the repo root, serve it in a **separate** nginx container (independent of the app stack):

```bash
make docker-web
```

- **URL:** [http://127.0.0.1:8765](http://127.0.0.1:8765)
- **Stop:** `make docker-web-down`

This uses `docker/docker-compose.web.yml` and bind-mounts `pyadminer-web/` read-only. The folder may be gitignored; it must exist on your machine for the mount to work.

---

## Option B: Virtual environment (app on host, MySQL elsewhere)

Use this when you already run MySQL (local install, cloud, or another container) and want to hack on PyAdminer with `pip` and your editor.

1. **Clone and create a venv**

   ```bash
   git clone https://github.com/anilpokhariyal/py-adminer.git
   cd py-adminer
   python3 -m venv .venv
   source .venv/bin/activate          # Windows: .venv\Scripts\activate
   ```

2. **Install dependencies** (includes dev tools: pytest, ruff)

   ```bash
   pip install -e ".[dev]"
   ```

   If `mysqlclient` fails to compile, install the OS packages from the table above and retry.

3. **Configure Flask**

   ```bash
   export FLASK_APP=main.py
   export SECRET_KEY="change-me-in-production"   # required for stable sessions outside toy dev
   ```

4. **Run the server**

   ```bash
   flask run
   ```

   Or:

   ```bash
   python main.py
   ```

   Defaults are described in the README (`FLASK_RUN_HOST`, `FLASK_RUN_PORT`, etc.).

5. **Log in through the UI**

   Use whatever host/port your MySQL listens on (e.g. `127.0.0.1` and `3306`, or a cloud hostname). Set `PYADMINER_DEFAULT_MYSQL_HOST` if you want the login form prefilled.

---

## Verify the install

- Open the app in a browser and complete the MySQL login form.
- **Health check** (no database session required):

  ```bash
  curl -sSf http://127.0.0.1:5000/health
  ```

  With Docker local compose, use port **8080** instead of `5000`.

  A typical response is JSON: `{"status":"ok"}`.

---

## Development checks

From the repo root, with the venv activated and dev dependencies installed:

```bash
ruff check pyadminer tests && ruff format --check pyadminer tests
pytest
```

Integration tests that need a real server run only when `MYSQL_TEST_HOST` is set (see `tests/conftest.py`). CI uses a MySQL service when workflows run on GitHub Actions.

---

## Other Docker layouts

`docker/docker-compose.yml` is oriented toward an external Docker network (e.g. Laradock-style setups). For a self-contained demo, prefer **`docker/docker-compose.local.yml`** as above.

---

## Configuration reference

All supported environment variables, read-only mode, HTTP Basic Auth, audit log path, rate limits, and AI-related toggles are documented in the **Configuration** section of the [README](../README.md).

AI provider keys are configured in the app (**AI** in the sidebar), not via environment variables (except `PYADMINER_AI_DISABLE` to turn AI off globally).
