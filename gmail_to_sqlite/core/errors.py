"""Custom exceptions for Gmail-to-SQLite AI chat."""


class ChatError(Exception):
    """Base exception for chat-related errors."""

    def __init__(self, message: str, suggestion: str = None):
        super().__init__(message)
        self.suggestion = suggestion


class ModelError(ChatError):
    """Exception for model-related errors."""

    def __init__(self, message: str, model: str = None, suggestion: str = None):
        super().__init__(message, suggestion)
        self.model = model


class DatabaseError(ChatError):
    """Exception for database-related errors."""

    def __init__(self, message: str, db_path: str = None, suggestion: str = None):
        super().__init__(message, suggestion)
        self.db_path = db_path


class ConfigurationError(ChatError):
    """Exception for configuration-related errors."""

    def __init__(self, message: str, config_key: str = None, suggestion: str = None):
        super().__init__(message, suggestion)
        self.config_key = config_key


class APIError(ChatError):
    """Exception for API-related errors."""

    def __init__(self, message: str, api_provider: str = None, suggestion: str = None):
        super().__init__(message, suggestion)
        self.api_provider = api_provider
