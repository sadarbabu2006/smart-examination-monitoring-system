"""Configuration for the Milestone 1 Flask application."""

import os
from pathlib import Path

from dotenv import load_dotenv


# config.py lives at <project-root>/backend/app/config.py.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def project_storage_path(environment_variable, default_relative_path):
    """Resolve a configured persistent path relative to the project, not the CWD."""
    configured_path = Path(os.getenv(environment_variable, default_relative_path))
    if not configured_path.is_absolute():
        configured_path = PROJECT_ROOT / configured_path
    return configured_path.resolve()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY") or os.urandom(32)
    DATABASE_PATH = str(project_storage_path("DATABASE_PATH", "database/examguard.db"))
    REGISTRATION_PHOTO_DIR = str(project_storage_path("REGISTRATION_PHOTO_DIR", "data/registration_photos"))
    JSON_SORT_KEYS = False


class TestingConfig(Config):
    TESTING = True
