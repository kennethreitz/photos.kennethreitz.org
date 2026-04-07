"""
ExifTree API — powered by django-bolt.

Run with: python manage.py runbolt --dev
OpenAPI docs available at /api/docs/
"""

from __future__ import annotations

import msgspec
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
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

from core.models import Camera, ExifData, Image, Lens, User
from gallery.models import Collection, CollectionImage
from groups.models import Group, GroupImage, GroupMembership
from ingest.tasks import process_image_task

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
    access: str
    refresh: str


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
    exif: ExifSchema | None = None


class ImageListSchema(msgspec.Struct):
    id: str
    title: str
    slug: str
    user: str
    upload_date: str
    thumbnail_small: str = ''


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


class CollectionUpdateInput(msgspec.Struct):
    title: str | None = None
    description: str | None = None
    visibility: str | None = None


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
    return ImageListSchema(
        id=str(img.id), title=img.title, slug=img.slug,
        user=img.user.username, upload_date=img.upload_date.isoformat(),
        thumbnail_small=img.thumbnail_small.url if img.thumbnail_small else '',
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
        exif=exif_data,
    )


def _public_images_qs():
    return (
        Image.objects.filter(
            visibility=Image.Visibility.PUBLIC,
            is_processing=False,
        )
        .select_related('user')
    )


# ---------------------------------------------------------------------------
# API setup
# ---------------------------------------------------------------------------

api = BoltAPI(prefix="/api")

auth_router = Router(prefix="/auth", tags=["auth"])
cameras_router = Router(prefix="/cameras", tags=["cameras"])
lenses_router = Router(prefix="/lenses", tags=["lenses"])
images_router = Router(prefix="/images", tags=["images"])
users_router = Router(prefix="/users", tags=["users"])
collections_router = Router(prefix="/collections", tags=["collections"])
groups_router = Router(prefix="/groups", tags=["groups"])
search_router = Router(prefix="/search", tags=["search"])


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@auth_router.post("/register")
async def register(data: RegisterInput) -> TokenSchema:
    if await User.objects.filter(username=data.username).aexists():
        return Response({"detail": "Username taken"}, status=409)
    if await User.objects.filter(email=data.email).aexists():
        return Response({"detail": "Email already registered"}, status=409)

    user = await User.objects.acreate(
        username=data.username,
        email=data.email,
        password=make_password(data.password),
    )
    tokens = create_jwt_for_user(user)
    return TokenSchema(access=tokens['access'], refresh=tokens['refresh'])


@auth_router.post("/login")
async def login(data: LoginInput) -> TokenSchema:
    user = await User.objects.filter(username=data.username).afirst()
    if not user or not user.check_password(data.password):
        return Response({"detail": "Invalid credentials"}, status=401)

    tokens = create_jwt_for_user(user)
    return TokenSchema(access=tokens['access'], refresh=tokens['refresh'])


@auth_router.get("/me", auth=[JWTAuthentication()], guards=[IsAuthenticated()])
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
async def list_cameras() -> list[CameraSchema]:
    cameras = []
    async for c in Camera.objects.annotate(
        image_count=Count('images')
    ).filter(image_count__gt=0).order_by('manufacturer', 'model'):
        cameras.append(_camera_schema(c, image_count=c.image_count))
    return cameras


@cameras_router.get("/{camera_id}")
async def get_camera(camera_id: str) -> CameraSchema:
    c = await Camera.objects.annotate(
        image_count=Count('images')
    ).aget(id=camera_id)
    return _camera_schema(c, image_count=c.image_count)


@cameras_router.get("/{camera_id}/images")
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
async def list_lenses() -> list[LensSchema]:
    lenses = []
    async for l in Lens.objects.annotate(
        image_count=Count('images')
    ).filter(image_count__gt=0).order_by('manufacturer', 'model'):
        lenses.append(_lens_schema(l, image_count=l.image_count))
    return lenses


@lenses_router.get("/{lens_id}")
async def get_lens(lens_id: str) -> LensSchema:
    l = await Lens.objects.annotate(
        image_count=Count('images')
    ).aget(id=lens_id)
    return _lens_schema(l, image_count=l.image_count)


@lenses_router.get("/{lens_id}/images")
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

@images_router.get("/{image_id}")
async def get_image(image_id: str) -> ImageSchema:
    img = await (
        Image.objects.select_related('user', 'exif', 'exif__camera', 'exif__lens')
        .aget(id=image_id, visibility=Image.Visibility.PUBLIC, is_processing=False)
    )
    return _image_schema(img)


@images_router.post(
    "/upload",
    auth=[JWTAuthentication()],
    guards=[IsAuthenticated()],
)
async def upload_image(
    request: Request,
    image: UploadFile,
    title: str = '',
    description: str = '',
) -> ImageSchema:
    from django.conf import settings
    from django.core.files.base import ContentFile

    contents = await image.read()
    if len(contents) > settings.MAX_UPLOAD_SIZE:
        return Response({"detail": "File too large"}, status=400)

    slug = slugify(title) if title else slugify(image.filename.rsplit('.', 1)[0])

    img = await Image.objects.acreate(
        user=request.user,
        title=title,
        description=description,
        slug=slug,
        original=ContentFile(contents, name=image.filename),
        is_processing=True,
    )

    process_image_task.delay(str(img.id))

    return Response(
        _image_schema(img),
        status=201,
    )


@images_router.patch(
    "/{image_id}",
    auth=[JWTAuthentication()],
    guards=[IsAuthenticated()],
)
async def update_image(request: Request, image_id: str, data: ImageUpdateInput) -> ImageSchema:
    img = await Image.objects.select_related('user').aget(id=image_id)
    if str(img.user_id) != str(request.user.id):
        return Response({"detail": "Not your image"}, status=403)

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
async def delete_image(request: Request, image_id: str):
    img = await Image.objects.aget(id=image_id)
    if str(img.user_id) != str(request.user.id):
        return Response({"detail": "Not your image"}, status=403)
    await img.adelete()
    return Response(status=204)


# ---------------------------------------------------------------------------
# Users (public profiles)
# ---------------------------------------------------------------------------

@users_router.get("/{username}")
async def get_user(username: str) -> UserSchema:
    u = await User.objects.aget(username=username)
    return _user_schema(u)


@users_router.get("/{username}/images")
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
            image_count=c.image_count,
        ))
    return collections


@collections_router.get("/{collection_id}")
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
async def create_collection(request: Request, data: CollectionCreateInput) -> CollectionSchema:
    c = await Collection.objects.acreate(
        user=request.user,
        title=data.title,
        slug=slugify(data.title),
        description=data.description,
        visibility=data.visibility,
    )
    return Response(
        CollectionSchema(
            id=str(c.id), title=c.title, slug=c.slug,
            description=c.description, visibility=c.visibility, image_count=0,
        ),
        status=201,
    )


@collections_router.patch(
    "/{collection_id}",
    auth=[JWTAuthentication()],
    guards=[IsAuthenticated()],
)
async def update_collection(
    request: Request, collection_id: str, data: CollectionUpdateInput,
) -> CollectionSchema:
    c = await Collection.objects.aget(id=collection_id)
    if str(c.user_id) != str(request.user.id):
        return Response({"detail": "Not your collection"}, status=403)

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

    await c.asave(update_fields=update_fields)
    count = await CollectionImage.objects.filter(collection=c).acount()
    return CollectionSchema(
        id=str(c.id), title=c.title, slug=c.slug,
        description=c.description, visibility=c.visibility, image_count=count,
    )


@collections_router.delete(
    "/{collection_id}",
    auth=[JWTAuthentication()],
    guards=[IsAuthenticated()],
)
async def delete_collection(request: Request, collection_id: str):
    c = await Collection.objects.aget(id=collection_id)
    if str(c.user_id) != str(request.user.id):
        return Response({"detail": "Not your collection"}, status=403)
    await c.adelete()
    return Response(status=204)


@collections_router.post(
    "/{collection_id}/images/{image_id}",
    auth=[JWTAuthentication()],
    guards=[IsAuthenticated()],
)
async def add_image_to_collection(request: Request, collection_id: str, image_id: str):
    c = await Collection.objects.aget(id=collection_id)
    if str(c.user_id) != str(request.user.id):
        return Response({"detail": "Not your collection"}, status=403)

    if await CollectionImage.objects.filter(collection=c, image_id=image_id).aexists():
        return Response({"detail": "Image already in collection"}, status=409)

    count = await CollectionImage.objects.filter(collection=c).acount()
    await CollectionImage.objects.acreate(
        collection=c, image_id=image_id, sort_order=count,
    )
    return Response(status=201)


@collections_router.delete(
    "/{collection_id}/images/{image_id}",
    auth=[JWTAuthentication()],
    guards=[IsAuthenticated()],
)
async def remove_image_from_collection(request: Request, collection_id: str, image_id: str):
    c = await Collection.objects.aget(id=collection_id)
    if str(c.user_id) != str(request.user.id):
        return Response({"detail": "Not your collection"}, status=403)

    deleted, _ = await CollectionImage.objects.filter(
        collection=c, image_id=image_id,
    ).adelete()
    if not deleted:
        return Response({"detail": "Image not in collection"}, status=404)
    return Response(status=204)


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

@groups_router.get("")
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
async def join_group(request: Request, slug: str):
    g = await Group.objects.aget(slug=slug)
    if g.visibility == Group.Visibility.PRIVATE:
        return Response({"detail": "Private group"}, status=403)

    if await GroupMembership.objects.filter(user=request.user, group=g).aexists():
        return Response({"detail": "Already a member"}, status=409)

    await GroupMembership.objects.acreate(
        user=request.user, group=g, role=GroupMembership.Role.MEMBER,
    )
    return Response(status=201)


@groups_router.post(
    "/{slug}/leave",
    auth=[JWTAuthentication()],
    guards=[IsAuthenticated()],
)
async def leave_group(request: Request, slug: str):
    deleted, _ = await GroupMembership.objects.filter(
        user=request.user, group__slug=slug,
    ).adelete()
    if not deleted:
        return Response({"detail": "Not a member"}, status=404)
    return Response(status=204)


@groups_router.post(
    "/{slug}/images/{image_id}",
    auth=[JWTAuthentication()],
    guards=[IsAuthenticated()],
)
async def submit_image_to_group(request: Request, slug: str, image_id: str):
    g = await Group.objects.aget(slug=slug)

    # Must be a member
    if not await GroupMembership.objects.filter(user=request.user, group=g).aexists():
        return Response({"detail": "Not a member"}, status=403)

    # Must own the image
    img = await Image.objects.aget(id=image_id)
    if str(img.user_id) != str(request.user.id):
        return Response({"detail": "Not your image"}, status=403)

    if await GroupImage.objects.filter(image=img, group=g).aexists():
        return Response({"detail": "Image already in group"}, status=409)

    await GroupImage.objects.acreate(image=img, group=g)
    return Response(status=201)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@search_router.get("")
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
