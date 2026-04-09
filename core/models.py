import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class SiteConfig(models.Model):
    """Singleton site configuration — only one row should ever exist."""
    site_title = models.CharField(max_length=255, default='ExifTree')
    tagline = models.CharField(
        max_length=255, blank=True,
        default="Browse photography through the gear that made it."
    )
    analytics_code = models.TextField(
        blank=True,
        help_text="Analytics snippet (GA, Gauges, etc.) — pasted into the &lt;head&gt; of every page",
    )
    openai_api_key = models.CharField(
        max_length=255, blank=True,
        help_text="OpenAI API key for AI image descriptions"
    )
    ai_prompt = models.TextField(
        blank=True,
        default="Describe this photograph in 2-3 sentences. Focus on the subject, mood, composition, and lighting. Be concise and evocative.",
        help_text="Prompt sent to the AI for image descriptions",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'site configuration'
        verbose_name_plural = 'site configuration'

    def __str__(self) -> str:
        return self.site_title

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> 'SiteConfig':
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bio = models.TextField(blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True)
    website = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # email is inherited from AbstractUser but we want it required
    email = models.EmailField("email address", unique=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return self.username


class Camera(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    manufacturer = models.CharField(max_length=255, db_index=True)
    model = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    display_name = models.CharField(max_length=512)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['manufacturer', 'model']
        unique_together = [('manufacturer', 'model')]

    def __str__(self) -> str:
        return self.display_name


class Lens(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    manufacturer = models.CharField(max_length=255, db_index=True)
    model = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    display_name = models.CharField(max_length=512)
    focal_length_min = models.PositiveIntegerField(
        null=True, blank=True, help_text="Minimum focal length in mm"
    )
    focal_length_max = models.PositiveIntegerField(
        null=True, blank=True, help_text="Maximum focal length in mm (same as min for primes)"
    )
    max_aperture = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'lenses'
        ordering = ['manufacturer', 'model']
        unique_together = [('manufacturer', 'model')]

    def __str__(self) -> str:
        return self.display_name


CONTINENT_MAP = {
    'AF': 'Africa', 'AN': 'Antarctica', 'AS': 'Asia', 'EU': 'Europe',
    'NA': 'North America', 'OC': 'Oceania', 'SA': 'South America',
}

# Country code to continent code
COUNTRY_TO_CONTINENT = {
    'AD': 'EU', 'AE': 'AS', 'AF': 'AS', 'AG': 'NA', 'AI': 'NA', 'AL': 'EU', 'AM': 'AS',
    'AO': 'AF', 'AR': 'SA', 'AS': 'OC', 'AT': 'EU', 'AU': 'OC', 'AW': 'NA', 'AZ': 'AS',
    'BA': 'EU', 'BB': 'NA', 'BD': 'AS', 'BE': 'EU', 'BF': 'AF', 'BG': 'EU', 'BH': 'AS',
    'BI': 'AF', 'BJ': 'AF', 'BM': 'NA', 'BN': 'AS', 'BO': 'SA', 'BR': 'SA', 'BS': 'NA',
    'BT': 'AS', 'BW': 'AF', 'BY': 'EU', 'BZ': 'NA', 'CA': 'NA', 'CD': 'AF', 'CF': 'AF',
    'CG': 'AF', 'CH': 'EU', 'CI': 'AF', 'CL': 'SA', 'CM': 'AF', 'CN': 'AS', 'CO': 'SA',
    'CR': 'NA', 'CU': 'NA', 'CV': 'AF', 'CY': 'EU', 'CZ': 'EU', 'DE': 'EU', 'DJ': 'AF',
    'DK': 'EU', 'DM': 'NA', 'DO': 'NA', 'DZ': 'AF', 'EC': 'SA', 'EE': 'EU', 'EG': 'AF',
    'ER': 'AF', 'ES': 'EU', 'ET': 'AF', 'FI': 'EU', 'FJ': 'OC', 'FK': 'SA', 'FM': 'OC',
    'FO': 'EU', 'FR': 'EU', 'GA': 'AF', 'GB': 'EU', 'GD': 'NA', 'GE': 'AS', 'GH': 'AF',
    'GI': 'EU', 'GL': 'NA', 'GM': 'AF', 'GN': 'AF', 'GQ': 'AF', 'GR': 'EU', 'GT': 'NA',
    'GU': 'OC', 'GW': 'AF', 'GY': 'SA', 'HK': 'AS', 'HN': 'NA', 'HR': 'EU', 'HT': 'NA',
    'HU': 'EU', 'ID': 'AS', 'IE': 'EU', 'IL': 'AS', 'IN': 'AS', 'IQ': 'AS', 'IR': 'AS',
    'IS': 'EU', 'IT': 'EU', 'JM': 'NA', 'JO': 'AS', 'JP': 'AS', 'KE': 'AF', 'KG': 'AS',
    'KH': 'AS', 'KI': 'OC', 'KM': 'AF', 'KN': 'NA', 'KP': 'AS', 'KR': 'AS', 'KW': 'AS',
    'KY': 'NA', 'KZ': 'AS', 'LA': 'AS', 'LB': 'AS', 'LC': 'NA', 'LI': 'EU', 'LK': 'AS',
    'LR': 'AF', 'LS': 'AF', 'LT': 'EU', 'LU': 'EU', 'LV': 'EU', 'LY': 'AF', 'MA': 'AF',
    'MC': 'EU', 'MD': 'EU', 'ME': 'EU', 'MG': 'AF', 'MH': 'OC', 'MK': 'EU', 'ML': 'AF',
    'MM': 'AS', 'MN': 'AS', 'MO': 'AS', 'MP': 'OC', 'MR': 'AF', 'MT': 'EU', 'MU': 'AF',
    'MV': 'AS', 'MW': 'AF', 'MX': 'NA', 'MY': 'AS', 'MZ': 'AF', 'NA': 'AF', 'NE': 'AF',
    'NG': 'AF', 'NI': 'NA', 'NL': 'EU', 'NO': 'EU', 'NP': 'AS', 'NR': 'OC', 'NZ': 'OC',
    'OM': 'AS', 'PA': 'NA', 'PE': 'SA', 'PG': 'OC', 'PH': 'AS', 'PK': 'AS', 'PL': 'EU',
    'PR': 'NA', 'PS': 'AS', 'PT': 'EU', 'PW': 'OC', 'PY': 'SA', 'QA': 'AS', 'RO': 'EU',
    'RS': 'EU', 'RU': 'EU', 'RW': 'AF', 'SA': 'AS', 'SB': 'OC', 'SC': 'AF', 'SD': 'AF',
    'SE': 'EU', 'SG': 'AS', 'SI': 'EU', 'SK': 'EU', 'SL': 'AF', 'SM': 'EU', 'SN': 'AF',
    'SO': 'AF', 'SR': 'SA', 'SS': 'AF', 'SV': 'NA', 'SY': 'AS', 'SZ': 'AF', 'TD': 'AF',
    'TG': 'AF', 'TH': 'AS', 'TJ': 'AS', 'TL': 'AS', 'TM': 'AS', 'TN': 'AF', 'TO': 'OC',
    'TR': 'AS', 'TT': 'NA', 'TV': 'OC', 'TW': 'AS', 'TZ': 'AF', 'UA': 'EU', 'UG': 'AF',
    'US': 'NA', 'UY': 'SA', 'UZ': 'AS', 'VA': 'EU', 'VC': 'NA', 'VE': 'SA', 'VG': 'NA',
    'VI': 'NA', 'VN': 'AS', 'VU': 'OC', 'WS': 'OC', 'YE': 'AS', 'ZA': 'AF', 'ZM': 'AF',
    'ZW': 'AF',
}

# Country code to full name
COUNTRY_NAMES = {
    'AD': 'Andorra', 'AE': 'UAE', 'AF': 'Afghanistan', 'AG': 'Antigua and Barbuda',
    'AL': 'Albania', 'AM': 'Armenia', 'AO': 'Angola', 'AR': 'Argentina', 'AT': 'Austria',
    'AU': 'Australia', 'AZ': 'Azerbaijan', 'BA': 'Bosnia', 'BB': 'Barbados', 'BD': 'Bangladesh',
    'BE': 'Belgium', 'BG': 'Bulgaria', 'BH': 'Bahrain', 'BR': 'Brazil', 'BS': 'Bahamas',
    'BT': 'Bhutan', 'BW': 'Botswana', 'BY': 'Belarus', 'BZ': 'Belize', 'CA': 'Canada',
    'CH': 'Switzerland', 'CL': 'Chile', 'CN': 'China', 'CO': 'Colombia', 'CR': 'Costa Rica',
    'CU': 'Cuba', 'CY': 'Cyprus', 'CZ': 'Czechia', 'DE': 'Germany', 'DK': 'Denmark',
    'DO': 'Dominican Republic', 'DZ': 'Algeria', 'EC': 'Ecuador', 'EE': 'Estonia', 'EG': 'Egypt',
    'ES': 'Spain', 'ET': 'Ethiopia', 'FI': 'Finland', 'FJ': 'Fiji', 'FR': 'France',
    'GB': 'United Kingdom', 'GE': 'Georgia', 'GH': 'Ghana', 'GR': 'Greece', 'GT': 'Guatemala',
    'HK': 'Hong Kong', 'HN': 'Honduras', 'HR': 'Croatia', 'HT': 'Haiti', 'HU': 'Hungary',
    'ID': 'Indonesia', 'IE': 'Ireland', 'IL': 'Israel', 'IN': 'India', 'IQ': 'Iraq',
    'IR': 'Iran', 'IS': 'Iceland', 'IT': 'Italy', 'JM': 'Jamaica', 'JO': 'Jordan',
    'JP': 'Japan', 'KE': 'Kenya', 'KH': 'Cambodia', 'KR': 'South Korea', 'KW': 'Kuwait',
    'KZ': 'Kazakhstan', 'LA': 'Laos', 'LB': 'Lebanon', 'LK': 'Sri Lanka', 'LT': 'Lithuania',
    'LU': 'Luxembourg', 'LV': 'Latvia', 'MA': 'Morocco', 'MC': 'Monaco', 'MD': 'Moldova',
    'ME': 'Montenegro', 'MK': 'North Macedonia', 'MM': 'Myanmar', 'MN': 'Mongolia',
    'MO': 'Macau', 'MT': 'Malta', 'MU': 'Mauritius', 'MV': 'Maldives', 'MX': 'Mexico',
    'MY': 'Malaysia', 'MZ': 'Mozambique', 'NA': 'Namibia', 'NG': 'Nigeria', 'NI': 'Nicaragua',
    'NL': 'Netherlands', 'NO': 'Norway', 'NP': 'Nepal', 'NZ': 'New Zealand', 'OM': 'Oman',
    'PA': 'Panama', 'PE': 'Peru', 'PH': 'Philippines', 'PK': 'Pakistan', 'PL': 'Poland',
    'PR': 'Puerto Rico', 'PT': 'Portugal', 'PY': 'Paraguay', 'QA': 'Qatar', 'RO': 'Romania',
    'RS': 'Serbia', 'RU': 'Russia', 'RW': 'Rwanda', 'SA': 'Saudi Arabia', 'SE': 'Sweden',
    'SG': 'Singapore', 'SI': 'Slovenia', 'SK': 'Slovakia', 'SN': 'Senegal', 'SO': 'Somalia',
    'TH': 'Thailand', 'TN': 'Tunisia', 'TR': 'Turkey', 'TT': 'Trinidad and Tobago',
    'TW': 'Taiwan', 'TZ': 'Tanzania', 'UA': 'Ukraine', 'UG': 'Uganda', 'US': 'United States',
    'UY': 'Uruguay', 'UZ': 'Uzbekistan', 'VE': 'Venezuela', 'VN': 'Vietnam', 'ZA': 'South Africa',
    'ZM': 'Zambia', 'ZW': 'Zimbabwe',
}


class City(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    region = models.CharField(max_length=255, blank=True, help_text="State/province/admin region")
    country_code = models.CharField(max_length=2, db_index=True)
    country = models.CharField(max_length=255)
    continent = models.CharField(max_length=20, db_index=True)
    slug = models.SlugField(max_length=255, unique=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'cities'
        ordering = ['continent', 'country', 'name']

    def __str__(self) -> str:
        return f"{self.name}, {self.country}"

    @classmethod
    def from_coordinates(cls, lat: float, lon: float) -> 'City | None':
        """Reverse geocode coordinates to a City, creating if needed."""
        import reverse_geocoder as rg
        from django.utils.text import slugify

        results = rg.search([(lat, lon)])
        if not results:
            return None
        r = results[0]

        cc = r['cc']

        # Reject known-bad GPS countries
        if cc in ('CN', 'IN', 'JP', 'KG', 'MN', 'RU'):
            return None

        continent_code = COUNTRY_TO_CONTINENT.get(cc, 'NA')
        continent = CONTINENT_MAP.get(continent_code, 'Unknown')
        country_name = COUNTRY_NAMES.get(cc, cc)
        region = r.get('admin1', '')

        # For US, use name (city) not admin2 (county)
        # For others, prefer admin2 (parent city) over name (suburb)
        city_name = r['name']
        admin2 = r.get('admin2', '')
        if cc != 'US' and admin2 and admin2 != city_name:
            city_name = admin2

        # Clean up common prefixes
        for prefix in ['City of ', 'Town of ', 'Village of ']:
            if city_name.startswith(prefix):
                city_name = city_name[len(prefix):]
        # Strip " County" suffix for US
        if cc == 'US' and city_name.endswith(' County'):
            city_name = city_name[:-7]

        slug = slugify(f"{city_name}-{region}-{cc}" if region else f"{city_name}-{cc}")

        city, _ = cls.objects.get_or_create(
            slug=slug,
            defaults={
                'name': city_name,
                'region': region,
                'country_code': cc,
                'country': country_name,
                'continent': continent,
                'latitude': float(r['lat']),
                'longitude': float(r['lon']),
            },
        )
        return city

    @property
    def display_name(self) -> str:
        """City, State for US; City for others."""
        if self.country_code == 'US' and self.region:
            return f"{self.name}, {self.region}"
        return self.name


class Tag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class Image(models.Model):
    class Visibility(models.TextChoices):
        PUBLIC = 'public', "Public"
        PRIVATE = 'private', "Private"
        UNLISTED = 'unlisted', "Unlisted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='images')
    title = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    ai_title = models.CharField(
        max_length=255, blank=True, help_text="AI-generated artistic title"
    )
    ai_description = models.TextField(
        blank=True, help_text="AI-generated description of the image"
    )
    slug = models.SlugField(max_length=255)
    original = models.ImageField(upload_to='originals/%Y/%m/')
    thumbnail_small = models.ImageField(upload_to='thumbs/small/', blank=True)
    thumbnail_medium = models.ImageField(upload_to='thumbs/medium/', blank=True)
    thumbnail_large = models.ImageField(upload_to='thumbs/large/', blank=True)
    visibility = models.CharField(
        max_length=10, choices=Visibility.choices, default=Visibility.PUBLIC
    )
    content_hash = models.CharField(
        max_length=64, blank=True, db_index=True,
        help_text="SHA-256 hash of the original file for deduplication"
    )
    perceptual_hash = models.CharField(
        max_length=16, blank=True, db_index=True,
        help_text="Perceptual hash for visual similarity detection"
    )
    city = models.ForeignKey(
        City, on_delete=models.SET_NULL, null=True, blank=True, related_name='images',
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name='images')
    view_count = models.PositiveIntegerField(default=0)
    is_processing = models.BooleanField(default=True)
    upload_date = models.DateTimeField(auto_now_add=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-upload_date']
        indexes = [
            models.Index(fields=['user', 'upload_date']),
            models.Index(fields=['visibility', 'upload_date']),
        ]

    def __str__(self) -> str:
        return self.title or f"Image {self.id}"


class ExifData(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    image = models.OneToOneField(Image, on_delete=models.CASCADE, related_name='exif')
    raw_data = models.JSONField(
        default=dict, help_text="Complete raw EXIF blob — never discard this"
    )
    camera = models.ForeignKey(
        Camera, on_delete=models.SET_NULL, null=True, blank=True, related_name='images'
    )
    lens = models.ForeignKey(
        Lens, on_delete=models.SET_NULL, null=True, blank=True, related_name='images'
    )
    focal_length = models.DecimalField(
        max_digits=7, decimal_places=1, null=True, blank=True,
        help_text="Focal length in mm"
    )
    aperture = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True,
        help_text="f-number"
    )
    shutter_speed = models.CharField(
        max_length=20, blank=True, help_text="e.g. 1/250, 2.5\""
    )
    iso = models.PositiveIntegerField(null=True, blank=True)
    date_taken = models.DateTimeField(null=True, blank=True, db_index=True)
    gps_latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    gps_longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'EXIF data'
        verbose_name_plural = 'EXIF data'
        indexes = [
            models.Index(fields=['camera', 'date_taken']),
            models.Index(fields=['lens', 'date_taken']),
            models.Index(fields=['focal_length']),
            models.Index(fields=['aperture']),
            models.Index(fields=['iso']),
        ]

    def __str__(self) -> str:
        return f"EXIF for {self.image}"
