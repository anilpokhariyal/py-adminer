import os

import pytest


@pytest.fixture
def app():
    from pyadminer import create_app

    app = create_app()
    app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        RATELIMIT_ENABLED=False,
    )
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(scope="session")
def mysql_env():
    """Set MYSQL_TEST_HOST etc. in CI; skip integration tests if unset."""
    host = os.environ.get("MYSQL_TEST_HOST", "").strip()
    if not host:
        pytest.skip("MYSQL_TEST_HOST not set (integration tests skipped)")
    return {
        "host": host,
        "port": int(os.environ.get("MYSQL_TEST_PORT", "3306")),
        "user": os.environ.get("MYSQL_TEST_USER", "root"),
        "password": os.environ.get("MYSQL_TEST_PASSWORD", "test"),
        "database": os.environ.get("MYSQL_TEST_DATABASE", "mysql"),
    }
