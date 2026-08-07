import os

from dotenv import load_dotenv

# Flask's CLI loads .env automatically, but a direct gunicorn/script run
# does not, so load it here explicitly.
load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    # ...
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL"
    ) or "sqlite:///" + os.path.join(basedir, "app.db")

    MAIL_SERVER = os.environ.get("MAIL_SERVER")
    MAIL_PORT = int(os.environ.get("MAIL_PORT") or 587)
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "1").lower() in ("1", "true", "yes")
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_FROM = os.environ.get("MAIL_FROM") or MAIL_USERNAME  # envelope sender
    ADMINS = ["louishabberfieldshort@gmail.com"]
