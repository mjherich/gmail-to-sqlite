"""
Central Dynaconf settings for gmail‑to‑sqlite.

Configuration is loaded from .secrets.toml and settings.toml files.
Configuration files should be in project root.
"""

from dynaconf import Dynaconf, Validator
from typing import Optional, Dict, Any

# Define validators for configuration integrity
validators = [
    # API Keys validation
    Validator(
        "OPENAI_API_KEY",
        must_exist=True,
        startswith="sk-",
        messages={
            "must_exist_true": "OPENAI_API_KEY is required for AI chat functionality"
        },
    ),
    Validator(
        "GOOGLE_API_KEY",
        must_exist=True,
        messages={
            "must_exist_true": "GOOGLE_API_KEY is required for Gemini chat functionality"
        },
    ),
    Validator(
        "ANTHROPIC_API_KEY",
        must_exist=True,
        startswith="sk-ant-",
        messages={
            "must_exist_true": "ANTHROPIC_API_KEY is required for Claude chat functionality"
        },
    ),
    # ACCOUNT validation - at least one account must exist
    Validator(
        "ACCOUNT",
        must_exist=True,
        is_type_of=list,
        len_min=1,
        messages={
            "must_exist_true": "At least one [[ACCOUNT]] entry must be defined in .secrets.toml"
        },
    ),
]

settings = Dynaconf(
    settings_files=["settings.toml", ".secrets.toml"],
    environments=False,  # Disable environment-specific settings
    envvar_prefix=False,  # Disable environment variable support
    load_dotenv=False,  # Disable .env file loading
    auto_cast=True,  # Automatically cast values to appropriate types
    validators=validators,
)


def get_user_config(account_name: str = "personal") -> Optional[Dict[str, Any]]:
    """
    Get user configuration for a specific account.

    Args:
        account_name: Name of the account to get config for

    Returns:
        Dictionary with user configuration or None if not found
    """
    accounts = settings.get("ACCOUNT", [])

    for account in accounts:
        if account.get("name") == account_name:
            return {
                "name": account.get("user_name"),
                "email": account.get("user_email"),
                "bio": account.get("bio"),
                "custom_instructions": account.get("custom_instructions"),
                "data_dir": account.get("data_dir"),
            }

    return None


def get_primary_account_config() -> Dict[str, Any]:
    """Get the primary account configuration (first account in list)."""
    accounts = settings.get("ACCOUNT", [])
    if not accounts:
        raise ValueError("No [[ACCOUNT]] entries configured in .secrets.toml")

    account = accounts[0]
    return {
        "name": account.get("user_name"),
        "email": account.get("user_email"),
        "bio": account.get("bio"),
        "custom_instructions": account.get("custom_instructions"),
        "data_dir": account.get("data_dir"),
        "account_name": account.get("name"),
    }
