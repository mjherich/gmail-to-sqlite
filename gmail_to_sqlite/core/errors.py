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


class ErrorHandler:
    """Centralized error handling for consistent user experience."""
    
    @staticmethod
    def handle_api_error(error: Exception) -> str:
        """Handle API-related errors with user-friendly messages."""
        error_type = type(error).__name__
        
        if "RateLimitError" in error_type:
            return (
                "⏳ Rate limit reached. Please wait a moment and try again.\n"
                "This can happen when making too many requests too quickly."
            )
        elif "AuthenticationError" in error_type:
            return "🔐 Authentication failed. Please check your API keys in .secrets.toml"
        elif "NotFoundError" in error_type:
            return (
                "🔍 Model not found or not available. Try switching to a different model.\n"
                "Use 'model' command to switch to: gemini, openai, or anthropic"
            )
        elif "TimeoutError" in error_type or "timeout" in str(error).lower():
            return (
                "⏱️ Request timed out. Please try again.\n"
                "This can happen with large queries or slow network connections."
            )
        elif "ConnectionError" in error_type or "connection" in str(error).lower():
            return (
                "🌐 Connection error. Please check your internet connection.\n"
                "If the problem persists, the API service may be temporarily unavailable."
            )
        else:
            return f"❌ Error: {error}"
    
    @staticmethod
    def handle_database_error(error: Exception) -> str:
        """Handle database-related errors."""
        error_str = str(error)
        
        if "no such table" in error_str.lower():
            return (
                "📂 Database table not found. Please sync your Gmail data first.\n"
                "Run: gmail-to-sqlite sync"
            )
        elif "database is locked" in error_str.lower():
            return (
                "🔒 Database is locked. Please wait a moment and try again.\n"
                "This can happen if another process is accessing the database."
            )
        elif "no such column" in error_str.lower():
            return (
                "📊 Database column not found. Your database schema may be outdated.\n"
                "Try running: gmail-to-sqlite sync --update-schema"
            )
        else:
            return f"💾 Database error: {error}"
    
    @staticmethod
    def handle_configuration_error(error: Exception) -> str:
        """Handle configuration-related errors."""
        error_str = str(error)
        
        if "api_key" in error_str.lower() or "key" in error_str.lower():
            return (
                "🔑 API key configuration error. Please check your .secrets.toml file.\n"
                "Ensure all required API keys are properly configured."
            )
        elif "account" in error_str.lower():
            return (
                "👤 Account configuration error. Please check your account settings.\n"
                "Run: gmail-to-sqlite sync --list-accounts"
            )
        else:
            return f"⚙️ Configuration error: {error}"
