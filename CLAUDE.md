# CLAUDE.md

## Project

**photos.kennethreitz.org** (codename: ExifTree) — a personal photography portfolio organized by gear, places, and subjects. AI-powered metadata, EXIF-based discovery, infinite scroll.

**Live:** https://photos.kennethreitz.org
**Repo:** github.com/kennethreitz/photos.kennethreitz.org
**Stack:** Django 6.x · Python 3.14 · PostgreSQL · Celery · django-bolt · Tigris (S3) · OpenAI
**Deploy:** Fly.io with GitHub Actions auto-deploy on push to main

## Architecture

Single-tenant. One owner account. No public registration, no multi-user features.

### Apps

- `core` — All models (User, Image, ExifData, Camera, Lens, Tag, City, SiteConfig). Other apps import from here but never the reverse.
- `tree` — Browse pages: cameras, lenses, tags, cities. No models, reads from core.
- `gallery` — Collections for organizing photos into curated sets.
- `ingest` — Upload pipeline, EXIF extraction, thumbnail generation, AI description, geocoding.
- `search` — Full-text search across titles, descriptions, AI fields, and tags.

### Image Pipeline (ingest)

1. Validate format/size
2. Extract EXIF
3. Normalize camera/lens (deduplicate manufacturer strings)
4. Compute perceptual hash (visual dedup)
5. Generate thumbnails (small 300px, medium 800px, large 1600px)
6. Create ExifData record
7. Reverse geocode GPS to city (offline, blocks invalid countries)
8. Apply cleanup rules (delete/fix based on date, country)
9. Mark processed
10. Dispatch AI description task (async via Celery)

### Cleanup Rules

Defined in `core/management/commands/cleanup.py` and enforced inline in `ingest/pipeline.py`:

**Delete:** years 2008, 2019, 2020. Dates: Dec 26 2014, Dec 22 2017.
**Fix:** clear `date_taken` for years before 2008 and 2021+ (incorrect EXIF dates).
**Cities:** block CN, JP, KG, MN, RU entirely. India allows only Bangalore/Mysore.

Invalid countries are blocked at four levels: `City.from_coordinates()`, `ingest/pipeline.py`, `geocode` command, and `cleanup` command.

### AI Metadata

GPT-4o-mini with structured output generates per-image:
- **Title** — short, evocative (3-7 words)
- **Description** — 2-3 sentences
- **Tags** — 5-10 single-word lowercase tags

Configured via SiteConfig admin (OpenAI key + custom prompt).

## Code Style

- Python: PEP 8, type hints on function signatures
- Django: fat models, thin views — logic lives on the model or in service functions
- Imports: stdlib → third-party → django → local apps, separated by blank lines
- Strings: double quotes for user-facing, single quotes for identifiers
- Templates: HTMX for interactivity, vanilla JS only where required (upload drag-drop, manage multi-select)
- Tests: use pytest + pytest-django

## Models

- UUIDField primary keys everywhere (not auto-increment)
- created_at/updated_at timestamps on every model
- SlugField on anything in a URL
- ExifData stores raw EXIF as JSONField — never throw away the raw data
- Camera/Lens are canonical: raw EXIF strings normalized via `core/normalization.py`

## Frontend

Django templates + HTMX. No frontend framework. Session auth. Minimal vanilla JS.

- Infinite scroll via HTMX `hx-trigger="revealed"` with stable shuffle per session
- CSS cache-busting via content hash in context processor
- Analytics snippet configurable in SiteConfig admin

## URLs

- `/` — home with infinite scroll, year filter
- `/cameras/`, `/cameras/<slug>/` — gear browsing
- `/lenses/`, `/lenses/<slug>/`
- `/tags/`, `/tags/<slug>/` — AI-generated tag cloud
- `/cities/`, `/cities/<slug>/` — GPS-based location browsing
- `/collections/`, `/collections/<slug>/`
- `/images/<uuid>/` — detail with EXIF bar, prev/next, keyboard nav
- `/manage/` — photo manager with multi-select, bulk actions, faceted filters
- `/upload/` — drag-drop upload with progress
- `/dashboard/` — owner dashboard
- `/search/` — full-text search with EXIF filters
- `/admin/` — Django admin (SiteConfig, models)

## Infrastructure

- **Fly.io**: two processes — `web` (django-bolt) + `worker` (celery -c 2)
- **PostgreSQL**: Fly Postgres (4GB dedicated). Also Celery broker via `sqla+postgresql://`
- **Tigris**: S3-compatible object storage for all images (used locally and in prod)
- **Redis**: local-only Celery broker (brew service). Not used in production.
- **GitHub Actions**: auto-deploy on push to main via `flyctl deploy --remote-only`
- **python-dotenv**: `.env` loaded automatically in `manage.py`

## Management Commands

```
import_folder /path   # Bulk import with auto-seek, dedup, concurrent workers
import_flickr <user>  # Import from Flickr via API
ai_describe           # Backfill AI metadata (--tail for continuous watch)
geocode               # Batch reverse geocode GPS to cities
cleanup               # Run all cleanup rules
dedupe                # Remove visual duplicates via perceptual hash
reprocess             # Re-process stuck images
```

## When Working on This

- Don't add dependencies without discussing tradeoffs
- Prefer Django builtins over third-party packages
- Write reversible migrations
- Keep core minimal — if logic could live in core or a feature app, default to the feature app
- Cleanup rules must be mirrored in both the cleanup command and pipeline.py
- Restart Celery workers after code changes (they cache old Python modules)
- `conn_max_age=60` and `CELERY_BROKER_POOL_LIMIT=1` to prevent DB connection exhaustion
