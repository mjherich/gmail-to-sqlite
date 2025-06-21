"""Model management and configuration for AI chat."""

from typing import Dict, Optional, Any
from dataclasses import dataclass

from crewai import LLM

from ..config import settings
from .errors import ModelError, ConfigurationError, APIError


@dataclass
class ModelConfig:
    """Configuration for an AI model."""
    key: str
    name: str
    full_identifier: str
    description: str
    features: str
    api_key_name: str
    api_url: Optional[str] = None
    default_temperature: float = 0.1
    max_retries: int = 3
    timeout: int = 30


class ModelManager:
    """Manages AI model configurations and instantiation."""
    
    # Model configurations following CrewAI best practices
    MODELS = {
        "gemini": ModelConfig(
            key="gemini",
            name="Gemini 2.0 Flash Exp",
            full_identifier="gemini/gemini-2.0-flash-exp",
            description="Latest & Advanced - Fast reasoning, large context",
            features="🚀 Fast, 🧠 Advanced reasoning, 📝 Large context",
            api_key_name="GOOGLE_API_KEY",
        ),
        "openai": ModelConfig(
            key="openai", 
            name="OpenAI GPT-4.1",
            full_identifier="openai/gpt-4.1",
            description="Latest & Most Capable - Balanced performance",
            features="⚡ Balanced, 🎯 Precise, 🛠️ Great tools",
            api_key_name="OPENAI_API_KEY",
        ),
        "anthropic": ModelConfig(
            key="anthropic",
            name="Claude 3.5 Sonnet", 
            full_identifier="anthropic/claude-3-5-sonnet-20241022",
            description="Most Capable - Superior reasoning and analysis",
            features="🧠 Superior reasoning, 📊 Analysis, 💡 Insights",
            api_key_name="ANTHROPIC_API_KEY",
        ),
    }
    
    # Model selection data for UI
    MODEL_SELECTION = {
        "1": {
            "key": "gemini",
            "name": "Gemini 2.0 Flash Exp",
            "description": "Latest & Advanced - Fast reasoning, large context",
            "features": "🚀 Fast, 🧠 Advanced reasoning"
        },
        "2": {
            "key": "openai", 
            "name": "OpenAI GPT-4.1",
            "description": "Latest & Most Capable - Balanced performance",
            "features": "⚡ Balanced, 🎯 Precise"
        },
        "3": {
            "key": "anthropic",
            "name": "Claude 3.5 Sonnet",
            "description": "Most Capable - Superior reasoning",
            "features": "🧠 Superior reasoning, 📊 Analysis"
        },
    }
    
    @classmethod
    def get_model_config(cls, model_key: str) -> ModelConfig:
        """Get model configuration by key."""
        if model_key not in cls.MODELS:
            available = ", ".join(cls.MODELS.keys())
            raise ModelError(
                f"Unknown model: {model_key}",
                model=model_key,
                suggestion=f"Available models: {available}"
            )
        return cls.MODELS[model_key]
    
    @classmethod
    def create_llm(cls, model_key: str, **kwargs) -> LLM:
        """Create and configure an LLM instance."""
        config = cls.get_model_config(model_key)
        
        # Validate API key
        api_key = settings.get(config.api_key_name)
        if not api_key:
            error_msg, suggestion = cls._get_api_key_error_info(config)
            raise ConfigurationError(error_msg, config.api_key_name, suggestion)
        
        # Merge configuration with any overrides
        llm_config = {
            "model": config.full_identifier,
            "api_key": api_key,
            "temperature": config.default_temperature,
            "max_retries": config.max_retries,
            "timeout": config.timeout,
            **kwargs  # Allow overrides
        }
        
        try:
            return LLM(**llm_config)
        except Exception as e:
            raise APIError(
                f"Failed to initialize {config.name}: {str(e)}",
                api_provider=config.key,
                suggestion="Check your API key and internet connection"
            )
    
    @classmethod
    def _get_api_key_error_info(cls, config: ModelConfig) -> tuple[str, str]:
        """Get detailed error message and suggestion for missing API key."""
        error_messages = {
            "GOOGLE_API_KEY": (
                f"Google API key not found. Please set {config.api_key_name} in .secrets.toml.",
                f'Add to .secrets.toml: {config.api_key_name} = "your-key-here"\n'
                "Get your API key from: https://aistudio.google.com/app/apikey"
            ),
            "OPENAI_API_KEY": (
                f"OpenAI API key not found. Please set {config.api_key_name} in .secrets.toml.",
                f'Add to .secrets.toml: {config.api_key_name} = "your-key-here"\n'
                "Get your API key from: https://platform.openai.com/api-keys"
            ),
            "ANTHROPIC_API_KEY": (
                f"Anthropic API key not found. Please set {config.api_key_name} in .secrets.toml.",
                f'Add to .secrets.toml: {config.api_key_name} = "your-key-here"\n'
                "Get your API key from: https://console.anthropic.com/"
            ),
        }
        
        return error_messages.get(
            config.api_key_name,
            (f"API key {config.api_key_name} not found.", "Check your configuration.")
        )
    
    @classmethod
    def validate_model_key(cls, model_key: str) -> bool:
        """Validate if a model key is supported."""
        return model_key in cls.MODELS
    
    @classmethod
    def get_model_description(cls, model_key: str) -> str:
        """Get human-readable model description."""
        config = cls.get_model_config(model_key)
        return f"{config.name} ({config.description})"
    
    @classmethod
    def list_available_models(cls) -> Dict[str, str]:
        """Get a mapping of model keys to descriptions."""
        return {
            key: f"{config.name} - {config.description}"
            for key, config in cls.MODELS.items()
        }