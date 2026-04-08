.PHONY: sync run migrate makemigrations bolt db worker

include .env
export

sync:
	uv sync

run: sync
	fly proxy 5432 -a exiftree-db &
	redis-server --daemonize yes 2>/dev/null || true
	uv run celery -A exiftree worker -l info -c 2 --detach --pidfile /tmp/exiftree-celery.pid 2>/dev/null || true
	sleep 1
	uv run python manage.py collectstatic --noinput 2>/dev/null
	uv run python manage.py runbolt --dev
	kill $$(cat /tmp/exiftree-celery.pid 2>/dev/null) 2>/dev/null || true
	kill %1 2>/dev/null || true
	redis-cli shutdown 2>/dev/null || true

bolt: sync
	uv run python manage.py runbolt --dev

migrate: sync
	uv run python manage.py migrate

makemigrations: sync
	uv run python manage.py makemigrations

db:
	fly proxy 5432 -a exiftree-db

worker: sync
	uv run celery -A exiftree worker -l info
