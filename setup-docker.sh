docker network create py_network || true && docker-compose -f docker/docker-compose.yml build py-adminer && docker-compose -f docker/docker-compose.yml up -d py-adminer
