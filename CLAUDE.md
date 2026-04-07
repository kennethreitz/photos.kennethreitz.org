# CLAUDE.md

## Project

ExifTree — a community platform where visual creators showcase work organized by the gear used to create it. Browse photography through cameras, lenses, and EXIF metadata.

**Domain:** exiftree.org
**Stack:** Django 5.x · Python 3.12+ · PostgreSQL · Celery + Redis
**Architecture doc:** `architecture.md`

## Code Style

- Python: follow PEP 8, use type hints on function signatures
- Django: fat models, thin views — business logic lives on the model or in service functions, not in views
- Imports: stdlib → third-party → django → local apps, separated by blank lines
- Strings: double quotes for user-facing text, single quotes for identifiers and dict keys
- Tests: use pytest + pytest-django, not unittest

## Project Layout

The Django project is created in the repo root (`django-admin startproject exiftree .`) — `manage.py` lives at the top level, not nested in a subdirectory.

## Django App Structure

The project is organized into focused Django apps:

- `core` — foundational models (User, Image, Camera, Lens, ExifData). Other apps import from here but never the reverse.
- `tree` — browse-by-gear discovery pages. No models, reads from core.
- `gallery` — user portfolios and collections.
- `groups` — community spaces and memberships.
- `ingest` — upload pipeline, EXIF extraction, thumbnail generation.
- `search` — EXIF-powered filtering and search.

**Dependency rule:** `core` depends on nothing. All other apps may depend on `core`. Avoid cross-dependencies between feature apps — if two apps need to share logic, it probably belongs in `core`.

## Models

- Always use `UUIDField` for primary keys (not auto-increment integers)
- Add `created_at` and `updated_at` timestamps to every model
- Use `SlugField` on anything that appears in a URL
- ExifData stores raw EXIF as a JSONField alongside parsed/indexed fields — never throw away the raw data
- Camera and Lens records are canonical/normalized — raw EXIF strings map to these via the normalization layer in `core/normalization.py`

## EXIF Normalization

This is critical infrastructure. EXIF strings are inconsistent across manufacturers. The normalization pipeline must:

- Strip redundant manufacturer prefixes ("NIKON CORPORATION NIKON D850" → "Nikon", "D850")
- Handle case normalization
- Deduplicate via a lookup table of known aliases
- Create new Camera/Lens records only when no match exists
- Be idempotent — running normalization twice on the same input produces the same result

## Image Pipeline

Uploads flow through `ingest`:

1. Validate format and size
2. Extract EXIF (Pillow / exifread)
3. Normalize camera/lens → core models
4. Generate thumbnails (small, medium, large)
5. Store originals + thumbnails in object storage (Cloudflare R2)
6. Create Image + ExifData records

All processing after initial validation happens async via Celery tasks. Never block the request/response cycle on image processing.

## Frontend

Django templates + HTMX for interactivity unless otherwise decided. Keep JavaScript minimal. The site should work without JS enabled for core browsing.

## Database

PostgreSQL. Key indexing priorities:

- ExifData: camera_id, lens_id, focal_length, aperture, iso, date_taken
- Image: user_id, upload_date, visibility
- Camera/Lens: slug, manufacturer

## URLs

- Camera tree: `/cameras/`, `/cameras/<manufacturer>/`, `/cameras/<manufacturer>/<model>/`
- Lens tree: `/lenses/`, `/lenses/<manufacturer>/<model>/`
- User profiles: `/@<username>/`
- Collections: `/@<username>/collections/<slug>/`
- Groups: `/groups/<slug>/`

## When Working on This Project

- Read `architecture.md` for full context on app structure and open decisions
- Don't add dependencies without discussing tradeoffs first
- Prefer Django's built-in tools over third-party packages when they're sufficient
- Write migrations that are reversible
- Keep the normalization lookup table in a format that's easy to contribute to (YAML or dict, not hardcoded if/else chains)
- If a piece of logic could live in core or a feature app, default to the feature app — keep core minimal
