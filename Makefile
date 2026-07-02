.PHONY: install up down logs update

install:
	bash install.sh

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f bot

update:
	git pull && docker compose up -d --build
