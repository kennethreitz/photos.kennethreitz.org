# ExifTree

A personal photography portfolio that organizes your work by the gear, places, and subjects that define it. Powered by EXIF metadata and AI.

**Live:** [photos.kennethreitz.org](https://photos.kennethreitz.org)

## Features

- **Browse by gear** — Every camera and lens gets its own page with infinite scroll
- **AI-powered metadata** — GPT-4o-mini generates titles, descriptions, and tags for every photo
- **Tag cloud** — Thousands of AI-generated tags with word cloud discovery
- **Cities** — GPS coordinates are reverse-geocoded to browsable locations, grouped by country and state
- **EXIF everywhere** — Camera, lens, focal length, aperture, shutter speed, ISO, date taken
- **Photo manager** — Bulk select, visibility controls, faceted filtering by camera/lens/year
- **Search** — Full-text across titles, AI descriptions, and tags
- **Infinite scroll** — Shuffled, session-stable ordering across all pages
- **Collections** — Organize photos into curated sets
- **Keyboard navigation** — Arrow keys between images, O for original download

## Stack

- **Django 6** + **django-bolt** (async ASGI server with API)
- **PostgreSQL** on Fly.io (also used as Celery broker)
- **Celery** for async image processing and AI description generation
- **Tigris** (S3-compatible) for image storage
- **HTMX** for infinite scroll, vanilla JS where needed
- **OpenAI** GPT-4o-mini with structured output for image metadata

## Management Commands

```
manage.py import_folder /path/to/photos     # Bulk import from disk
manage.py import_flickr <username>           # Import from Flickr
manage.py ai_describe                        # Backfill AI descriptions
manage.py ai_describe --tail                 # Watch and describe new images
manage.py geocode                            # Reverse geocode GPS to cities
manage.py cleanup                            # Run cleanup rules
manage.py dedupe                             # Remove visual duplicates
manage.py reprocess                          # Re-process stuck images
```

## Development

```
brew install redis
brew services start redis
cp .env.example .env  # Configure DATABASE_URL, AWS keys, etc.
make run
```

## Deployment

Deployed on [Fly.io](https://fly.io) with two processes (web + worker).

```
fly deploy
```
