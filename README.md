# PyAdminer
PyAdminer is a Python based database query interface. you can manage your database and perform all the operations like read write delete and update with a user friendly interface. It's a open source project, so anyone can contribute to this with feature updates, security updates and suggestions for improvement. This project can be setup either with venv or docker. easy setup instructions for both are added in the readme.

<h4>Setting Up project</h4>
To setup project on your system, please follow these steps:

<strong>Step 1:</strong> Download repository<br>
<strong>Step 2:</strong> Activate virtual env using command: "source venv/bin/activate"
expecting you running on ubuntu, otherwise please find right command 
for your OS.<br>
<strong>Step 3:</strong> Set flask_app env by executing command: "export FLASK_APP=main.py"<br>
<strong>Step 4:</strong> Run your application by command: "FLASK run".

<strong>Note:</strong> Bind address and port for local runs use environment variables <code>FLASK_RUN_HOST</code> and <code>FLASK_RUN_PORT</code> (defaults <code>0.0.0.0:5000</code>). Set a stable <code>SECRET_KEY</code> in production. Optional: <code>PYADMINER_READ_ONLY</code>, <code>PYADMINER_AUTH_USERNAME</code> / <code>PYADMINER_AUTH_PASSWORD</code>, <code>RATELIMIT_STORAGE_URI</code>. See <a href="docs/PROJECT_IMPROVEMENT_PLAN.md">docs/PROJECT_IMPROVEMENT_PLAN.md</a>.

<p><strong>Dependencies:</strong> <code>mysqlclient</code> needs MySQL/MariaDB client headers (e.g. on Ubuntu: <code>sudo apt install default-libmysqlclient-dev pkg-config</code>). Then: <code>pip install -e .</code> or <code>pip install -r requirements.txt</code>.</p>


<p>
  <strong>Docker (local):</strong> from the repo root run <code>make docker-local</code> (or <code>docker compose -f docker/docker-compose.local.yml up --build -d</code>). App: <code>http://127.0.0.1:8080</code>. The compose file bind-mounts the project and enables <code>FLASK_DEBUG=1</code> so Python/template edits reload without rebuilding; rebuild with the same command after changing <code>requirements.txt</code> or <code>docker/Dockerfile</code>. Use <code>make docker-local-restart</code> to restart only the app container. The older Laradock-oriented <code>setup-docker.sh</code> / <code>docker/docker-compose.yml</code> is optional.
  </p>
