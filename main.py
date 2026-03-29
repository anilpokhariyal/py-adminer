"""WSGI entrypoint for PyAdminer."""

import logging

from pyadminer import create_app
from pyadminer.config import get_host_port

app = create_app()

logging.getLogger("pyadminer.audit").setLevel(logging.INFO)

if __name__ == "__main__":
    host, port = get_host_port()
    app.run(debug=app.config.get("DEBUG", False), host=host, port=port)
