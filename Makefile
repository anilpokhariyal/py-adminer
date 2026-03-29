# Local Docker stack (PyAdminer + MySQL)
DOCKER_COMPOSE := docker compose -f docker/docker-compose.local.yml
DOCKER_COMPOSE_WEB := docker compose -f docker/docker-compose.web.yml

# Docker Hub image for the static marketing site (requires pyadminer-web/ on disk)
DOCKERHUB_USER ?= anilpokhariya
WEB_IMAGE := $(DOCKERHUB_USER)/pyadminer-web

.PHONY: docker-local docker-local-down docker-local-logs docker-local-restart docker-web docker-web-down docker-web-image docker-web-push

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

# Static marketing site (pyadminer-web/ — gitignored; must exist on host)
docker-web:
	$(DOCKER_COMPOSE_WEB) up -d

docker-web-down:
	$(DOCKER_COMPOSE_WEB) down

# Build image with site files baked in (from repo root; pyadminer-web/ required)
docker-web-image:
	docker build -f docker/Dockerfile.pyadminer-web -t $(WEB_IMAGE):latest .

# Push to Docker Hub (run: docker login) — override user: make docker-web-push DOCKERHUB_USER=you
docker-web-push: docker-web-image
	docker push $(WEB_IMAGE):latest
