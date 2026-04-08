.PHONY: sync run migrate makemigrations bolt db

include .env
export

sync:
	uv sync

run: sync
	fly proxy 5432 -a exiftree-db &
	sleep 1
	uv run python manage.py runbolt --dev
	kill %1 2>/dev/null || true

bolt: sync
	uv run python manage.py runbolt --dev

migrate: sync
	uv run python manage.py migrate

makemigrations: sync
	uv run python manage.py makemigrations

db:
	fly proxy 5432 -a exiftree-db
