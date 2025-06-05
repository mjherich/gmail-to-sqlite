"""
Central Dynaconf settings for gmail‑to‑sqlite.

Configuration is loaded from .secrets.toml and settings.toml files.
Configuration files should be in project root.
"""

from dynaconf import Dynaconf

settings = Dynaconf(
    settings_files=["settings.toml", ".secrets.toml"],
    environments=False,  # Disable environment-specific settings
    envvar_prefix=False,  # Disable environment variable support
    load_dotenv=False,  # Disable .env file loading
    auto_cast=True,  # Automatically cast values to appropriate types
)
