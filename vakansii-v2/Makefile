.PHONY: local-up local-down logs migrate worker-once

local-up:
	docker-compose up -d --build

local-down:
	docker-compose down -v

logs:
	docker-compose logs -f

migrate:
	docker-compose exec db psql -U jobs -d jobs_db -f /docker-entrypoint-initdb.d/schema.sql

worker-once:
	docker-compose run --rm worker python worker.py
