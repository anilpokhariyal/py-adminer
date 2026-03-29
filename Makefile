# Local Docker stack (PyAdminer + MySQL)
DOCKER_COMPOSE := docker compose -f docker/docker-compose.local.yml

.PHONY: docker-local docker-local-down docker-local-logs docker-local-restart

# Rebuild images if needed and start (run after Dockerfile or requirements.txt changes)
docker-local:
	$(DOCKER_COMPOSE) up --build -d

docker-local-down:
	$(DOCKER_COMPOSE) down

docker-local-logs:
	$(DOCKER_COMPOSE) logs -f py-adminer

# Pick up bind-mounted code without rebuild (e.g. if the reloader did not restart)
docker-local-restart:
	$(DOCKER_COMPOSE) restart py-adminer
