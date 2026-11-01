import os
from pathlib import Path
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Läses bara in om filen finns - i Docker sätts miljövariabler via
# env_file/environment i compose istället, så .env saknas där (avsiktligt,
# se .gitignore). Lokal körning utan Docker (README:s "Körning"-avsnitt)
# förlitar sig på den här filen, annars faller DEBUG tillbaka till False
# (produktionsläge) och statiska filer kräver ett collectstatic som aldrig
# körs lokalt.
load_dotenv(BASE_DIR / ".env")

DATA_DIR = Path(os.getenv("EXPENSEVIBE_DATA_DIR", str(BASE_DIR)))


def _env_flag(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value in {"1", "true", "True", "yes", "on"}


def _split_csv_env(name, default=""):
    return [value.strip() for value in os.getenv(name, default).split(",") if value.strip()]


def _public_url():
    return os.getenv("EXPENSEVIBE_PUBLIC_URL", "").strip()


def _allowed_hosts():
    # localhost/127.0.0.1/[::1] läggs alltid till, oavsett vad
    # DJANGO_ALLOWED_HOSTS är satt till - web-tjänstens egen healthcheck
    # (docker-compose.yml) anropar sig själv på just localhost inifrån
    # containern. Det är riskfritt att alltid tillåta: porten är bara
    # exponerad internt i Docker-nätverket (`expose`, inte `ports`), så en
    # extern anropare kan aldrig få ett request fram med de Host-headrarna
    # ändå. Utan detta avvisar Django healthcheckens egna anrop med
    # DisallowedHost så fort DJANGO_ALLOWED_HOSTS satts till en riktig
    # domän, och web blir aldrig "healthy".
    internal_hosts = ["127.0.0.1", "localhost", "[::1]"]

    explicit_hosts = _split_csv_env("DJANGO_ALLOWED_HOSTS")
    if explicit_hosts:
        return explicit_hosts + internal_hosts

    public_url = _public_url()
    if public_url:
        parsed_url = urlparse(public_url)
        if parsed_url.hostname:
            return [parsed_url.hostname] + internal_hosts

    return internal_hosts


def _csrf_trusted_origins():
    explicit_origins = _split_csv_env("DJANGO_CSRF_TRUSTED_ORIGINS")
    if explicit_origins:
        return explicit_origins

    public_url = _public_url()
    if public_url:
        parsed_url = urlparse(public_url)
        if parsed_url.scheme and parsed_url.netloc:
            return [f"{parsed_url.scheme}://{parsed_url.netloc}"]

    return []


# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = _env_flag("DJANGO_DEBUG", default=False)

# SECURITY WARNING: keep the secret key used in production secret!
# The fallback below is public (it is in version control), so it is only
# used with DEBUG on - without DEBUG a missing DJANGO_SECRET_KEY is fatal.
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY måste sättas när DJANGO_DEBUG inte är på.")
    SECRET_KEY = "django-insecure-expensevibe-dev-only-2f8f0e5b7c9a4d3e"

ALLOWED_HOSTS = _allowed_hosts()
# Adressen i appens QR-kod (accounts.views.mobile_app); bakom en proxy som
# tappar X-Forwarded-Proto ser Django annars http fast sajten är https.
EXPENSEVIBE_PUBLIC_URL = _public_url()

CSRF_TRUSTED_ORIGINS = _csrf_trusted_origins()

USE_X_FORWARDED_HOST = _env_flag("DJANGO_USE_X_FORWARDED_HOST", default=True)
if _env_flag("DJANGO_USE_SECURE_PROXY_SSL_HEADER", default=True):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

CSRF_COOKIE_SECURE = _env_flag("DJANGO_CSRF_COOKIE_SECURE", default=False)
SESSION_COOKIE_SECURE = _env_flag("DJANGO_SESSION_COOKIE_SECURE", default=False)


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "core",
    "attachments",
    "expenses",
    "mileage",
    "absence",
    "export",
    "api",
]

AUTH_USER_MODEL = "accounts.CustomUser"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.ForcePasswordChangeMiddleware",
]

ROOT_URLCONF = "expensevibe.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.nav_counts",
            ],
        },
    },
]

WSGI_APPLICATION = "expensevibe.wsgi.application"


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASE_ENGINE = os.getenv("DATABASE_ENGINE", "django.db.backends.sqlite3")

if DATABASE_ENGINE == "django.db.backends.sqlite3":
    DATABASES = {
        "default": {
            "ENGINE": DATABASE_ENGINE,
            "NAME": DATA_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": DATABASE_ENGINE,
            "NAME": os.getenv("DATABASE_NAME", "expensevibe"),
            "USER": os.getenv("DATABASE_USER", "expensevibe"),
            "PASSWORD": os.getenv("DATABASE_PASSWORD", ""),
            "HOST": os.getenv("DATABASE_HOST", "localhost"),
            "PORT": os.getenv("DATABASE_PORT", "5432"),
        }
    }


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = "sv-se"
TIME_ZONE = "Europe/Stockholm"
USE_I18N = True

# USE_THOUSAND_SEPARATOR applies locale grouping to *every* bare numeric template
# variable, not just money amounts - including primary keys used in <option value>,
# data-* attributes and URL query params. Money/amount displays instead force
# grouping explicitly via `|floatformat:'Ng'` where needed.
DECIMAL_SEPARATOR = ","
THOUSAND_SEPARATOR = " "
NUMBER_GROUPING = 3
USE_THOUSAND_SEPARATOR = False

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = "static/"
STATIC_ROOT = Path(os.getenv("EXPENSEVIBE_STATIC_ROOT", str(DATA_DIR / "staticfiles")))

_VENDOR_STATICFILES_DIRS = [
    ("vendor/bootstrap", BASE_DIR / "node_modules" / "bootstrap" / "dist"),
    ("vendor/bootstrap-icons", BASE_DIR / "node_modules" / "bootstrap-icons" / "font"),
]

STATICFILES_DIRS = [BASE_DIR / "static"]

# node_modules is build-time only in the production image (npm ci + collectstatic
# run in the builder stage, node_modules itself is never copied to the runtime
# image) - skip the vendor dirs there instead of firing staticfiles.W004 on every
# management command once the manifest is already built.
if (BASE_DIR / "node_modules").is_dir():
    STATICFILES_DIRS += _VENDOR_STATICFILES_DIRS

MEDIA_URL = "/media/"
MEDIA_ROOT = DATA_DIR / "media"

# CompressedManifestStaticFilesStorage requires a manifest built by
# collectstatic - fine in production (built during the Docker image build),
# but would break `runserver`/`test` in local dev where collectstatic is
# never run. Plain StaticFilesStorage needs no manifest and serves directly
# from STATICFILES_DIRS instead.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

# A receipt/faktura upload is rarely more than a few MB; 10 MB leaves headroom
# for a multi-page scanned PDF without letting a runaway upload exhaust memory.
DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv("EXPENSEVIBE_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
FILE_UPLOAD_MAX_MEMORY_SIZE = DATA_UPLOAD_MAX_MEMORY_SIZE

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "attachments": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "export": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}


# ReInvGrabber: separat internt program (eget repo) som föreslår bokförings-
# /betalningsfält ur en uppladdad bilaga med lokal OCR - se
# attachments/extraction_client.py. Tom sträng = avstängt, inget anrop görs
# alls och bilageuppladdning fungerar precis som utan integrationen.
REINVGRABBER_URL = os.getenv("REINVGRABBER_URL", "")
REINVGRABBER_TIMEOUT = int(os.getenv("REINVGRABBER_TIMEOUT", "15"))
