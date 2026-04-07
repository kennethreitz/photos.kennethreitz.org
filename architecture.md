# ExifTree — Architecture

**Domain:** exiftree.org  
**Stack:** Django · PostgreSQL · Python  
**Tagline:** Browse photography through the gear that made it.

---

## Concept

ExifTree is a community platform where visual creators showcase their work, organized around the gear used to create it. Click a camera name and see images from that camera across all users. Click a lens and browse the world through that glass.

EXIF metadata is the infrastructure — extracted automatically on upload, normalized into a browsable tree of cameras, lenses, and settings.

---

## Django Apps

### `core`

Owns the fundamental data models that everything else depends on. If you deleted every other app, `core` would still make sense on its own.

**Models:**

- `User` — extends AbstractUser. Username, email, bio, avatar, website URL, join date.
- `Image` — the uploaded work. Title, description, file path, thumbnail paths, upload date, visibility (public/private/unlisted), view count. FK to User.
- `Camera` — canonical camera record. Manufacturer, model, slug, display name. Normalized from raw EXIF strings.
- `Lens` — canonical lens record. Manufacturer, model, slug, display name, focal length range, max aperture. Normalized from raw EXIF strings.
- `ExifData` — one-to-one with Image. Raw EXIF blob (JSONField) plus parsed/indexed fields: FK to Camera, FK to Lens, focal length, aperture, shutter speed, ISO, date taken, GPS (nullable).

**Normalization layer:** EXIF strings are messy. "NIKON CORPORATION NIKON D850" and "Nikon D850" need to resolve to the same Camera record. Core owns a normalization pipeline — a lookup table of known aliases plus heuristics for splitting manufacturer/model. This can start as a simple mapping dict and evolve into something smarter over time.

---

### `tree`

The flagship feature. Browse-by-gear discovery pages.

**Routes:**

- `/cameras/` — grid of all cameras with image counts and sample thumbnails
- `/cameras/<manufacturer>/` — all models from one brand
- `/cameras/<manufacturer>/<model>/` — gallery of all images shot on this camera
- `/lenses/` — same structure for lenses
- `/lenses/<manufacturer>/<model>/`

**No new models.** Tree reads entirely from `core` models. It's a views/templates app that queries Camera, Lens, Image, and ExifData.

**Sorting/filtering within a camera page:** recent, most viewed, by lens, by focal length, by ISO range. All derived from ExifData fields.

---

### `gallery`

User-facing portfolios and collections.

**Models:**

- `Collection` — user-curated set of images. Title, description, cover image, ordering, visibility. FK to User.
- `CollectionImage` — M2M through table. FK to Collection, FK to Image, sort order.

**Routes:**

- `/@<username>/` — user profile, shows their uploads
- `/@<username>/collections/` — their collections
- `/@<username>/collections/<slug>/` — single collection view

---

### `groups`

Community spaces. Not in core because the platform works without them.

**Models:**

- `Group` — name, slug, description, cover image, created date, visibility (public/private/invite-only).
- `GroupMembership` — FK to User, FK to Group, role (member/moderator/admin), join date.
- `GroupImage` — FK to Image, FK to Group, submitted date. An image can belong to multiple groups.

**Routes:**

- `/groups/` — browse/search groups
- `/groups/<slug>/` — group page with member images
- `/groups/<slug>/members/` — member list

**Open question:** Can groups be auto-generated from gear? e.g., "Fujifilm X100V Shooters" as a system group that anyone who uploads an X100V image is implicitly part of. Could blur the line between `tree` and `groups` in an interesting way.

---

### `ingest`

The upload and processing pipeline. Handles the heavy lifting so other apps don't have to.

**Responsibilities:**

1. Accept image upload (validate format, size limits)
2. Extract EXIF via Pillow / exifread
3. Run normalization — resolve Camera and Lens records
4. Generate thumbnail variants (small, medium, large)
5. Store original in object storage (S3/R2/B2)
6. Store thumbnails in object storage
7. Create Image + ExifData records in core

**Processing:** Celery task queue for async processing. Upload returns immediately, processing happens in background. Image marked as "processing" until complete.

**Bulk import:** Future feature — ingest from Lightroom catalogs, Flickr exports, or directories with EXIF intact.

---

### `search`

EXIF-powered search and filtering. Builds on top of core models.

**Capabilities:**

- Full-text search on image title/description
- Filter by camera, lens, focal length range, aperture range, ISO range, date range
- Filter by GPS/location (if present)
- Combined queries: "all images shot on 85mm f/1.4 between ISO 100-400"

**Implementation:** Start with Django ORM queries + Postgres indexes. Move to Elasticsearch/Meilisearch if needed at scale.

---

## Infrastructure

### Image Storage

- **Originals:** Object storage (Cloudflare R2 preferred — no egress fees). Never serve originals directly.
- **Thumbnails:** Generated on upload in 3 sizes. Served via CDN.
- **CDN:** Cloudflare in front of R2. Images are the bulk of bandwidth.

### Database

PostgreSQL. Key indexes:

- ExifData: camera_id, lens_id, focal_length, aperture, iso, date_taken
- Image: user_id, upload_date, visibility
- Camera/Lens: slug, manufacturer

JSONField on ExifData stores the full raw EXIF blob for future use without migrations.

### Task Queue

Celery + Redis for async image processing. Tasks:

- EXIF extraction
- Thumbnail generation
- Camera/Lens normalization and dedup

### DNS / Hosting

- **DNS:** DNSimple (registered)
- **App hosting:** TBD — Railway, Render, or DigitalOcean for MVP
- **Object storage:** Cloudflare R2
- **CDN:** Cloudflare

---

## Repo Structure

```
exiftree/
├── manage.py
├── exiftree/
│   ├── settings/
│   │   ├── base.py
│   │   ├── dev.py
│   │   └── prod.py
│   ├── urls.py
│   └── wsgi.py
├── core/
│   ├── models.py
│   ├── admin.py
│   ├── normalization.py    # EXIF string → canonical Camera/Lens
│   ├── exif.py             # extraction logic
│   └── migrations/
├── tree/
│   ├── views.py
│   ├── urls.py
│   └── templates/tree/
├── gallery/
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   └── templates/gallery/
├── groups/
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   └── templates/groups/
├── ingest/
│   ├── tasks.py            # Celery tasks
│   ├── pipeline.py
│   ├── views.py            # upload endpoints
│   └── urls.py
├── search/
│   ├── views.py
│   ├── filters.py
│   ├── urls.py
│   └── templates/search/
├── static/
├── templates/              # base templates, shared partials
├── pyproject.toml          # uv-managed dependencies
├── uv.lock
└── docker-compose.yml
```

---

## Open Decisions

- **Frontend approach:** Django templates + HTMX for interactivity, or a separate SPA? HTMX keeps things simple and Pythonic. SPA gives richer interactions but doubles the stack.
- **Auth:** Django built-in vs django-allauth for social login.
- **Image formats:** Accept RAW files? Or JPEG/PNG/WebP only? RAW adds storage cost and processing complexity.
- **Moderation:** Community platform needs content moderation. Manual review queue? AI-assisted? Report system?
- **API:** REST API from day one (DRF) or add it later? Needed if a mobile app is ever on the table.
- **Auto-groups from gear:** Should the tree pages and groups merge in some way? A camera page is basically a group without the social features.
