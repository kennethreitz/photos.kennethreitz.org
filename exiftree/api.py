"""
ExifTree API — powered by django-bolt.

Run with: python manage.py runbolt --dev
OpenAPI docs available at /api/docs/
"""

from __future__ import annotations

from typing import Annotated

import msgspec
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.db import models
from django.db.models import Count
from django.utils.text import slugify
from django_bolt import (
    BoltAPI,
    IsAuthenticated,
    JWTAuthentication,
    Request,
    Response,
    Router,
    UploadFile,
    create_jwt_for_user,
)
from django_bolt.params import File
from django_bolt import rate_limit

from core.models import Camera, ExifData, Image, Lens, User
from gallery.models import Collection, CollectionImage
from groups.models import Group, GroupImage, GroupMembership
from ingest.tasks import process_image_task

# Rate limits (requests per second per IP)
RATE_READ = 100
RATE_WRITE = 20
RATE_AUTH = 10
RATE_UPLOAD = 200
RATE_SEARCH = 50

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ErrorSchema(msgspec.Struct):
    detail: str


# Auth
class RegisterInput(msgspec.Struct):
    username: str
    email: str
    password: str


class LoginInput(msgspec.Struct):
    username: str
    password: str


class TokenSchema(msgspec.Struct):
    token: str


class UserSchema(msgspec.Struct):
    id: str
    username: str
    bio: str
    website: str
    avatar: str = ''


class UserDetailSchema(msgspec.Struct):
    id: str
    username: str
    email: str
    bio: str
    website: str
    avatar: str = ''
    image_count: int = 0
    collection_count: int = 0


class ProfileUpdateInput(msgspec.Struct):
    bio: str | None = None
    website: str | None = None


# Gear
class CameraSchema(msgspec.Struct):
    id: str
    manufacturer: str
    model: str
    slug: str
    display_name: str
    image_count: int = 0


class LensSchema(msgspec.Struct):
    id: str
    manufacturer: str
    model: str
    slug: str
    display_name: str
    max_aperture: float | None = None
    image_count: int = 0


# EXIF / Images
class ExifSchema(msgspec.Struct):
    camera: CameraSchema | None = None
    lens: LensSchema | None = None
    focal_length: float | None = None
    aperture: float | None = None
    shutter_speed: str = ''
    iso: int | None = None
    date_taken: str | None = None


class ImageSchema(msgspec.Struct):
    id: str
    title: str
    slug: str
    description: str
    user: UserSchema
    visibility: str
    upload_date: str
    view_count: int
    is_processing: bool = False
    thumbnail_small: str = ''
    thumbnail_medium: str = ''
    thumbnail_large: str = ''
    original: str = ''
    exif: ExifSchema | None = None


class ImageListSchema(msgspec.Struct):
    id: str
    title: str
    slug: str
    user: str
    upload_date: str
    thumbnail_small: str = ''
    thumbnail_medium: str = ''
    thumbnail_large: str = ''
    camera: str = ''
    lens: str = ''
    focal_length: float | None = None
    aperture: float | None = None
    iso: int | None = None


class ImageUpdateInput(msgspec.Struct):
    title: str | None = None
    description: str | None = None
    visibility: str | None = None


# Collections
class CollectionSchema(msgspec.Struct):
    id: str
    title: str
    slug: str
    description: str
    visibility: str
    date: str | None = None
    created_at: str = ''
    image_count: int = 0


class CollectionDetailSchema(msgspec.Struct):
    id: str
    title: str
    slug: str
    description: str
    visibility: str
    user: UserSchema
    images: list[ImageListSchema] = []


class CollectionCreateInput(msgspec.Struct):
    title: str
    description: str = ''
    visibility: str = 'public'
    date: str | None = None


class CollectionUpdateInput(msgspec.Struct):
    title: str | None = None
    description: str | None = None
    visibility: str | None = None
    date: str | None = None


# Groups
class GroupSchema(msgspec.Struct):
    id: str
    name: str
    slug: str
    description: str
    visibility: str
    member_count: int = 0


class GroupDetailSchema(msgspec.Struct):
    id: str
    name: str
    slug: str
    description: str
    visibility: str
    member_count: int = 0
    members: list[MemberSchema] = []


class MemberSchema(msgspec.Struct):
    username: str
    role: str
    joined_at: str


# Search
class SearchResultSchema(msgspec.Struct):
    images: list[ImageListSchema]
    total: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_schema(u: User) -> UserSchema:
    return UserSchema(
        id=str(u.id), username=u.username, bio=u.bio, website=u.website,
        avatar=u.avatar.url if u.avatar else '',
    )


def _camera_schema(c: Camera, image_count: int = 0) -> CameraSchema:
    return CameraSchema(
        id=str(c.id), manufacturer=c.manufacturer, model=c.model,
        slug=c.slug, display_name=c.display_name, image_count=image_count,
    )


def _lens_schema(l: Lens, image_count: int = 0) -> LensSchema:
    return LensSchema(
        id=str(l.id), manufacturer=l.manufacturer, model=l.model,
        slug=l.slug, display_name=l.display_name,
        max_aperture=float(l.max_aperture) if l.max_aperture else None,
        image_count=image_count,
    )


def _image_list_schema(img: Image) -> ImageListSchema:
    camera = ''
    lens = ''
    focal_length = None
    aperture = None
    iso = None
    try:
        exif = img.exif
        if exif:
            if exif.camera:
                camera = exif.camera.display_name
            if exif.lens:
                lens = exif.lens.display_name
            focal_length = float(exif.focal_length) if exif.focal_length else None
            aperture = float(exif.aperture) if exif.aperture else None
            iso = exif.iso
    except Exception:
        pass
    return ImageListSchema(
        id=str(img.id), title=img.title, slug=img.slug,
        user=img.user.username, upload_date=img.upload_date.isoformat(),
        thumbnail_small=img.thumbnail_small.url if img.thumbnail_small else '',
        thumbnail_medium=img.thumbnail_medium.url if img.thumbnail_medium else '',
        thumbnail_large=img.thumbnail_large.url if img.thumbnail_large else '',
        camera=camera, lens=lens, focal_length=focal_length,
        aperture=aperture, iso=iso,
    )


def _image_schema(img: Image) -> ImageSchema:
    exif_data = None
    try:
        exif = img.exif
        exif_data = ExifSchema(
            camera=_camera_schema(exif.camera) if exif.camera else None,
            lens=_lens_schema(exif.lens) if exif.lens else None,
            focal_length=float(exif.focal_length) if exif.focal_length else None,
            aperture=float(exif.aperture) if exif.aperture else None,
            shutter_speed=exif.shutter_speed,
            iso=exif.iso,
            date_taken=exif.date_taken.isoformat() if exif.date_taken else None,
        )
    except ExifData.DoesNotExist:
        pass

    return ImageSchema(
        id=str(img.id), title=img.title, slug=img.slug,
        description=img.description, user=_user_schema(img.user),
        visibility=img.visibility, upload_date=img.upload_date.isoformat(),
        view_count=img.view_count, is_processing=img.is_processing,
        thumbnail_small=img.thumbnail_small.url if img.thumbnail_small else '',
        thumbnail_medium=img.thumbnail_medium.url if img.thumbnail_medium else '',
        thumbnail_large=img.thumbnail_large.url if img.thumbnail_large else '',
        original=img.original.url if img.original else '',
        exif=exif_data,
    )


def _public_images_qs():
    return (
        Image.objects.filter(
            visibility=Image.Visibility.PUBLIC,
            is_processing=False,
        )
        .select_related('user', 'exif', 'exif__camera', 'exif__lens')
    )


# ---------------------------------------------------------------------------
# API setup
# ---------------------------------------------------------------------------

api = BoltAPI()

auth_router = Router(prefix="/api/auth", tags=["auth"])
cameras_router = Router(prefix="/api/cameras", tags=["cameras"])
lenses_router = Router(prefix="/api/lenses", tags=["lenses"])
images_router = Router(prefix="/api/images", tags=["images"])
users_router = Router(prefix="/api/users", tags=["users"])
collections_router = Router(prefix="/api/collections", tags=["collections"])
groups_router = Router(prefix="/api/groups", tags=["groups"])
search_router = Router(prefix="/api/search", tags=["search"])


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@auth_router.post("/register")
@rate_limit(rps=RATE_AUTH, key="ip")
async def register(data: RegisterInput):
    if await User.objects.filter(username=data.username).aexists():
        return Response({"detail": "Username taken"}, status_code=409)
    if await User.objects.filter(email=data.email).aexists():
        return Response({"detail": "Email already registered"}, status_code=409)

    user = await User.objects.acreate(
        username=data.username,
        email=data.email,
        password=make_password(data.password),
    )
    token = create_jwt_for_user(user)
    return TokenSchema(token=token)


@auth_router.post("/login")
@rate_limit(rps=RATE_AUTH, key="ip")
async def login(data: LoginInput):
    user = await User.objects.filter(username=data.username).afirst()
    if not user or not user.check_password(data.password):
        return Response({"detail": "Invalid credentials"}, status_code=401)

    token = create_jwt_for_user(user)
    return TokenSchema(token=token)


@auth_router.get("/me", auth=[JWTAuthentication()], guards=[IsAuthenticated()])
@rate_limit(rps=RATE_READ, key="ip")
async def me(request: Request) -> UserDetailSchema:
    u = request.user
    image_count = await Image.objects.filter(user=u).acount()
    collection_count = await Collection.objects.filter(user=u).acount()
    return UserDetailSchema(
        id=str(u.id), username=u.username, email=u.email,
        bio=u.bio, website=u.website,
        avatar=u.avatar.url if u.avatar else '',
        image_count=image_count, collection_count=collection_count,
    )


@auth_router.patch("/me", auth=[JWTAuthentication()], guards=[IsAuthenticated()])
@rate_limit(rps=RATE_WRITE, key="ip")
async def update_profile(request: Request, data: ProfileUpdateInput) -> UserDetailSchema:
    u = request.user
    if data.bio is not None:
        u.bio = data.bio
    if data.website is not None:
        u.website = data.website
    await u.asave(update_fields=['bio', 'website', 'updated_at'])
    return await me(request)


# ---------------------------------------------------------------------------
# Cameras
# ---------------------------------------------------------------------------

@cameras_router.get("")
@rate_limit(rps=RATE_READ, key="ip")
async def list_cameras() -> list[CameraSchema]:
    cameras = []
    async for c in Camera.objects.annotate(
        image_count=Count('images')
    ).filter(image_count__gt=0).order_by('manufacturer', 'model'):
        cameras.append(_camera_schema(c, image_count=c.image_count))
    return cameras


@cameras_router.get("/{camera_id}")
@rate_limit(rps=RATE_READ, key="ip")
async def get_camera(camera_id: str) -> CameraSchema:
    c = await Camera.objects.annotate(
        image_count=Count('images')
    ).aget(id=camera_id)
    return _camera_schema(c, image_count=c.image_count)


@cameras_router.get("/{camera_id}/images")
@rate_limit(rps=RATE_READ, key="ip")
async def camera_images(camera_id: str) -> list[ImageListSchema]:
    images = []
    qs = _public_images_qs().filter(
        exif__camera_id=camera_id,
    ).order_by('-upload_date')[:50]
    async for img in qs:
        images.append(_image_list_schema(img))
    return images


# ---------------------------------------------------------------------------
# Lenses
# ---------------------------------------------------------------------------

@lenses_router.get("")
@rate_limit(rps=RATE_READ, key="ip")
async def list_lenses() -> list[LensSchema]:
    lenses = []
    async for l in Lens.objects.annotate(
        image_count=Count('images')
    ).filter(image_count__gt=0).order_by('manufacturer', 'model'):
        lenses.append(_lens_schema(l, image_count=l.image_count))
    return lenses


@lenses_router.get("/{lens_id}")
@rate_limit(rps=RATE_READ, key="ip")
async def get_lens(lens_id: str) -> LensSchema:
    l = await Lens.objects.annotate(
        image_count=Count('images')
    ).aget(id=lens_id)
    return _lens_schema(l, image_count=l.image_count)


@lenses_router.get("/{lens_id}/images")
@rate_limit(rps=RATE_READ, key="ip")
async def lens_images(lens_id: str) -> list[ImageListSchema]:
    images = []
    qs = _public_images_qs().filter(
        exif__lens_id=lens_id,
    ).order_by('-upload_date')[:50]
    async for img in qs:
        images.append(_image_list_schema(img))
    return images


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

@images_router.get("/explore")
@rate_limit(rps=RATE_READ, key="ip")
async def explore_images(limit: int = 48) -> list[ImageListSchema]:
    images = []
    qs = _public_images_qs().order_by('?')[:limit]
    async for img in qs:
        images.append(_image_list_schema(img))
    return images


@images_router.get("/{image_id}")
@rate_limit(rps=RATE_READ, key="ip")
async def get_image(image_id: str):
    try:
        img = await (
            Image.objects.select_related('user', 'exif', 'exif__camera', 'exif__lens')
            .aget(id=image_id, visibility=Image.Visibility.PUBLIC)
        )
    except Image.DoesNotExist:
        return Response({"detail": "Image not found"}, status_code=404)
    # Increment view count
    await Image.objects.filter(id=image_id).aupdate(view_count=models.F('view_count') + 1)
    img.view_count += 1
    return _image_schema(img)


@images_router.post(
    "/upload",
    auth=[JWTAuthentication()],
    guards=[IsAuthenticated()],
)
@rate_limit(rps=RATE_UPLOAD, key="ip")
async def upload_image(
    request: Request,
    image: Annotated[UploadFile, File(max_size=50_000_000)],
    title: str = '',
    description: str = '',
):
    from django.conf import settings
    from django.core.files.base import ContentFile
    from asgiref.sync import sync_to_async

    import hashlib

    contents = await image.read()
    if len(contents) > settings.MAX_UPLOAD_SIZE:
        return Response({"detail": "File too large"}, status_code=400)

    content_hash = hashlib.sha256(contents).hexdigest()

    # Check for exact duplicate
    existing = await Image.objects.filter(content_hash=content_hash).afirst()
    if existing:
        return Response({"detail": "Duplicate image", "id": str(existing.id)}, status_code=409)

    # Check for perceptual duplicate
    import imagehash
    from PIL import Image as PILImage
    from io import BytesIO
    pil_img = PILImage.open(BytesIO(contents))
    phash = str(imagehash.phash(pil_img))
    pil_img.close()

    # Exact phash match
    existing = await Image.objects.filter(perceptual_hash=phash).afirst()
    if existing:
        return Response({"detail": "Visually similar image already exists", "id": str(existing.id)}, status_code=409)

    # Fuzzy phash match (hamming distance <= 10)
    upload_hash = imagehash.hex_to_hash(phash)
    async for candidate in Image.objects.exclude(perceptual_hash='').exclude(perceptual_hash='8000000000000000'):
        if imagehash.hex_to_hash(candidate.perceptual_hash) - upload_hash <= 10:
            return Response({"detail": "Visually similar image already exists", "id": str(candidate.id)}, status_code=409)

    slug = slugify(title) if title else slugify(image.filename.rsplit('.', 1)[0])

    @sync_to_async
    def _create_and_dispatch():
        img = Image.objects.create(
            user=request.user,
            title=title,
            description=description,
            slug=slug,
            original=ContentFile(contents, name=image.filename),
            content_hash=content_hash,
            is_processing=True,
        )
        try:
            process_image_task.apply_async(args=[str(img.id)], ignore_result=True)
        except Exception:
            # No Redis/Celery — process synchronously
            from ingest.pipeline import process_image
            process_image(img)
        return img

    img = await _create_and_dispatch()

    # Image was just created — no exif yet, build a simple response
    return Response(
        ImageSchema(
            id=str(img.id), title=img.title, slug=img.slug,
            description=img.description, user=_user_schema(request.user),
            visibility=img.visibility, upload_date=img.upload_date.isoformat(),
            view_count=0, is_processing=True,
        ),
        status_code=201,
    )


@images_router.patch(
    "/{image_id}",
    auth=[JWTAuthentication()],
    guards=[IsAuthenticated()],
)
@rate_limit(rps=RATE_WRITE, key="ip")
async def update_image(request: Request, image_id: str, data: ImageUpdateInput):
    img = await Image.objects.select_related('user').aget(id=image_id)
    if str(img.user_id) != str(request.user.id):
        return Response({"detail": "Not your image"}, status_code=403)

    update_fields = ['updated_at']
    if data.title is not None:
        img.title = data.title
        img.slug = slugify(data.title)
        update_fields += ['title', 'slug']
    if data.description is not None:
        img.description = data.description
        update_fields.append('description')
    if data.visibility is not None:
        img.visibility = data.visibility
        update_fields.append('visibility')

    await img.asave(update_fields=update_fields)
    return _image_schema(img)


@images_router.delete(
    "/{image_id}",
    auth=[JWTAuthentication()],
    guards=[IsAuthenticated()],
)
@rate_limit(rps=RATE_WRITE, key="ip")
async def delete_image(request: Request, image_id: str):
    img = await Image.objects.aget(id=image_id)
    if str(img.user_id) != str(request.user.id):
        return Response({"detail": "Not your image"}, status_code=403)
    await img.adelete()
    return Response({}, status_code=204)


# ---------------------------------------------------------------------------
# Users (public profiles)
# ---------------------------------------------------------------------------

@users_router.get("")
@rate_limit(rps=RATE_READ, key="ip")
async def list_users(q: str = '') -> list[UserSchema]:
    users = []
    qs = User.objects.order_by('-created_at')
    if q:
        qs = qs.filter(username__icontains=q)
    async for u in qs[:50]:
        users.append(_user_schema(u))
    return users


@users_router.get("/{username}")
@rate_limit(rps=RATE_READ, key="ip")
async def get_user(username: str) -> UserSchema:
    u = await User.objects.aget(username=username)
    return _user_schema(u)


@users_router.get("/{username}/images")
@rate_limit(rps=RATE_READ, key="ip")
async def user_images(username: str) -> list[ImageListSchema]:
    images = []
    qs = _public_images_qs().filter(
        user__username=username,
    ).order_by('-upload_date')[:50]
    async for img in qs:
        images.append(_image_list_schema(img))
    return images


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------

@collections_router.get("/user/{username}")
@rate_limit(rps=RATE_READ, key="ip")
async def user_collections(username: str) -> list[CollectionSchema]:
    collections = []
    qs = Collection.objects.filter(
        user__username=username,
        visibility=Image.Visibility.PUBLIC,
    ).annotate(image_count=Count('collection_images')).order_by('-created_at')
    async for c in qs:
        collections.append(CollectionSchema(
            id=str(c.id), title=c.title, slug=c.slug,
            description=c.description, visibility=c.visibility,
            date=str(c.date) if c.date else None,
            created_at=c.created_at.isoformat(),
            image_count=c.image_count,
        ))
    return collections


@collections_router.get("/{collection_id}")
@rate_limit(rps=RATE_READ, key="ip")
async def get_collection(collection_id: str) -> CollectionDetailSchema:
    c = await Collection.objects.select_related('user').aget(id=collection_id)
    images = []
    qs = (
        Image.objects.filter(collection_entries__collection=c, is_processing=False)
        .select_related('user')
        .order_by('collection_entries__sort_order')
    )
    async for img in qs:
        images.append(_image_list_schema(img))

    return CollectionDetailSchema(
        id=str(c.id), title=c.title, slug=c.slug,
        description=c.description, visibility=c.visibility,
        user=_user_schema(c.user), images=images,
    )


@collections_router.post(
    "",
    auth=[JWTAuthentication()],
    guards=[IsAuthenticated()],
)
@rate_limit(rps=RATE_WRITE, key="ip")
async def create_collection(request: Request, data: CollectionCreateInput):
    import uuid as _uuid
    base_slug = slugify(data.title) or 'collection'
    slug = base_slug
    # Ensure unique slug per user
    while await Collection.objects.filter(user=request.user, slug=slug).aexists():
        slug = f"{base_slug}-{str(_uuid.uuid4())[:8]}"

    from datetime import date as _date
    date_val = None
    if data.date:
        try:
            date_val = _date.fromisoformat(data.date)
        except ValueError:
            pass

    c = await Collection.objects.acreate(
        user=request.user,
        title=data.title,
        slug=slug,
        description=data.description,
        visibility=data.visibility,
        date=date_val,
    )
    return Response(
        CollectionSchema(
            id=str(c.id), title=c.title, slug=c.slug,
            description=c.description, visibility=c.visibility,
            date=str(c.date) if c.date else None,
            created_at=c.created_at.isoformat(),
            image_count=0,
        ),
        status_code=201,
    )


@collections_router.patch(
    "/{collection_id}",
    auth=[JWTAuthentication()],
    guards=[IsAuthenticated()],
)
@rate_limit(rps=RATE_WRITE, key="ip")
async def update_collection(
    request: Request, collection_id: str, data: CollectionUpdateInput,
):
    c = await Collection.objects.aget(id=collection_id)
    if str(c.user_id) != str(request.user.id):
        return Response({"detail": "Not your collection"}, status_code=403)

    update_fields = ['updated_at']
    if data.title is not None:
        c.title = data.title
        c.slug = slugify(data.title)
        update_fields += ['title', 'slug']
    if data.description is not None:
        c.description = data.description
        update_fields.append('description')
    if data.visibility is not None:
        c.visibility = data.visibility
        update_fields.append('visibility')
    if data.date is not None:
        from datetime import date as _date
        try:
            c.date = _date.fromisoformat(data.date) if data.date else None
        except ValueError:
            c.date = None
        update_fields.append('date')

    await c.asave(update_fields=update_fields)
    count = await CollectionImage.objects.filter(collection=c).acount()
    return CollectionSchema(
        id=str(c.id), title=c.title, slug=c.slug,
        description=c.description, visibility=c.visibility,
        date=str(c.date) if c.date else None,
        created_at=c.created_at.isoformat(),
        image_count=count,
    )


@collections_router.delete(
    "/{collection_id}",
    auth=[JWTAuthentication()],
    guards=[IsAuthenticated()],
)
@rate_limit(rps=RATE_WRITE, key="ip")
async def delete_collection(request: Request, collection_id: str):
    c = await Collection.objects.aget(id=collection_id)
    if str(c.user_id) != str(request.user.id):
        return Response({"detail": "Not your collection"}, status_code=403)
    await c.adelete()
    return Response({}, status_code=204)


@collections_router.post(
    "/{collection_id}/images/{image_id}",
    auth=[JWTAuthentication()],
    guards=[IsAuthenticated()],
)
@rate_limit(rps=RATE_WRITE, key="ip")
async def add_image_to_collection(request: Request, collection_id: str, image_id: str):
    c = await Collection.objects.aget(id=collection_id)
    if str(c.user_id) != str(request.user.id):
        return Response({"detail": "Not your collection"}, status_code=403)

    if await CollectionImage.objects.filter(collection=c, image_id=image_id).aexists():
        return Response({"detail": "Image already in collection"}, status_code=409)

    count = await CollectionImage.objects.filter(collection=c).acount()
    await CollectionImage.objects.acreate(
        collection=c, image_id=image_id, sort_order=count,
    )
    return Response({}, status_code=201)


@collections_router.delete(
    "/{collection_id}/images/{image_id}",
    auth=[JWTAuthentication()],
    guards=[IsAuthenticated()],
)
@rate_limit(rps=RATE_WRITE, key="ip")
async def remove_image_from_collection(request: Request, collection_id: str, image_id: str):
    c = await Collection.objects.aget(id=collection_id)
    if str(c.user_id) != str(request.user.id):
        return Response({"detail": "Not your collection"}, status_code=403)

    deleted, _ = await CollectionImage.objects.filter(
        collection=c, image_id=image_id,
    ).adelete()
    if not deleted:
        return Response({"detail": "Image not in collection"}, status_code=404)
    return Response({}, status_code=204)


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

@groups_router.get("")
@rate_limit(rps=RATE_READ, key="ip")
async def list_groups() -> list[GroupSchema]:
    groups = []
    qs = (
        Group.objects.filter(visibility=Group.Visibility.PUBLIC)
        .annotate(member_count=Count('memberships'))
        .order_by('-created_at')
    )
    async for g in qs:
        groups.append(GroupSchema(
            id=str(g.id), name=g.name, slug=g.slug,
            description=g.description, visibility=g.visibility,
            member_count=g.member_count,
        ))
    return groups


@groups_router.get("/{slug}")
@rate_limit(rps=RATE_READ, key="ip")
async def get_group(slug: str) -> GroupDetailSchema:
    g = await Group.objects.annotate(
        member_count=Count('memberships')
    ).aget(slug=slug)

    members = []
    async for m in g.memberships.select_related('user').order_by('role', 'joined_at'):
        members.append(MemberSchema(
            username=m.user.username, role=m.role,
            joined_at=m.joined_at.isoformat(),
        ))

    return GroupDetailSchema(
        id=str(g.id), name=g.name, slug=g.slug,
        description=g.description, visibility=g.visibility,
        member_count=g.member_count, members=members,
    )


@groups_router.get("/{slug}/images")
@rate_limit(rps=RATE_READ, key="ip")
async def group_images(slug: str) -> list[ImageListSchema]:
    images = []
    qs = _public_images_qs().filter(
        group_entries__group__slug=slug,
    ).order_by('-group_entries__submitted_at')[:50]
    async for img in qs:
        images.append(_image_list_schema(img))
    return images


@groups_router.post(
    "/{slug}/join",
    auth=[JWTAuthentication()],
    guards=[IsAuthenticated()],
)
@rate_limit(rps=RATE_WRITE, key="ip")
async def join_group(request: Request, slug: str):
    g = await Group.objects.aget(slug=slug)
    if g.visibility == Group.Visibility.PRIVATE:
        return Response({"detail": "Private group"}, status_code=403)

    if await GroupMembership.objects.filter(user=request.user, group=g).aexists():
        return Response({"detail": "Already a member"}, status_code=409)

    await GroupMembership.objects.acreate(
        user=request.user, group=g, role=GroupMembership.Role.MEMBER,
    )
    return Response({}, status_code=201)


@groups_router.post(
    "/{slug}/leave",
    auth=[JWTAuthentication()],
    guards=[IsAuthenticated()],
)
@rate_limit(rps=RATE_WRITE, key="ip")
async def leave_group(request: Request, slug: str):
    deleted, _ = await GroupMembership.objects.filter(
        user=request.user, group__slug=slug,
    ).adelete()
    if not deleted:
        return Response({"detail": "Not a member"}, status_code=404)
    return Response({}, status_code=204)


@groups_router.post(
    "/{slug}/images/{image_id}",
    auth=[JWTAuthentication()],
    guards=[IsAuthenticated()],
)
@rate_limit(rps=RATE_WRITE, key="ip")
async def submit_image_to_group(request: Request, slug: str, image_id: str):
    g = await Group.objects.aget(slug=slug)

    # Must be a member
    if not await GroupMembership.objects.filter(user=request.user, group=g).aexists():
        return Response({"detail": "Not a member"}, status_code=403)

    # Must own the image
    img = await Image.objects.aget(id=image_id)
    if str(img.user_id) != str(request.user.id):
        return Response({"detail": "Not your image"}, status_code=403)

    if await GroupImage.objects.filter(image=img, group=g).aexists():
        return Response({"detail": "Image already in group"}, status_code=409)

    await GroupImage.objects.acreate(image=img, group=g)
    return Response({}, status_code=201)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@search_router.get("")
@rate_limit(rps=RATE_SEARCH, key="ip")
async def search_images(
    q: str = '',
    camera: str = '',
    lens: str = '',
    focal_min: float | None = None,
    focal_max: float | None = None,
    aperture_min: float | None = None,
    aperture_max: float | None = None,
    iso_min: int | None = None,
    iso_max: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> SearchResultSchema:
    qs = _public_images_qs()

    if q:
        from django.db.models import Q
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
    if camera:
        qs = qs.filter(exif__camera_id=camera)
    if lens:
        qs = qs.filter(exif__lens_id=lens)
    if focal_min is not None:
        qs = qs.filter(exif__focal_length__gte=focal_min)
    if focal_max is not None:
        qs = qs.filter(exif__focal_length__lte=focal_max)
    if aperture_min is not None:
        qs = qs.filter(exif__aperture__gte=aperture_min)
    if aperture_max is not None:
        qs = qs.filter(exif__aperture__lte=aperture_max)
    if iso_min is not None:
        qs = qs.filter(exif__iso__gte=iso_min)
    if iso_max is not None:
        qs = qs.filter(exif__iso__lte=iso_max)

    total = await qs.acount()
    images = []
    async for img in qs.order_by('-upload_date')[offset:offset + limit]:
        images.append(_image_list_schema(img))

    return SearchResultSchema(images=images, total=total)


# ---------------------------------------------------------------------------
# Wire up routers
# ---------------------------------------------------------------------------

api.include_router(auth_router)
api.include_router(cameras_router)
api.include_router(lenses_router)
api.include_router(images_router)
api.include_router(users_router)
api.include_router(collections_router)
api.include_router(groups_router)
api.include_router(search_router)

# Mount Django views (admin, templates) as fallback for non-API routes
api.mount_django("/", clear_root_path=True)
