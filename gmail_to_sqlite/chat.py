"""
Modern multi-turn chat interface using AI agents for Gmail data analysis.

This module provides a beautifully designed interactive chat CLI where users can have
ongoing conversations with specialized AI agents for analyzing Gmail data.

This is the new implementation with:
- Beautiful terminal UI using Rich library
- Modular agent architecture following CrewAI best practices
- Enhanced error handling and user feedback
- Persistent conversation memory
- Multiple AI model support (Gemini, OpenAI, Claude)
- Intelligent SQL generation with visual feedback

For backward compatibility, all original functions are maintained.
"""

import logging
from typing import Optional

# Import the new modular implementation
from .core import ChatSession
from .core.errors import ChatError
from .core.models import ModelManager

logger = logging.getLogger(__name__)


def setup_chat_logging() -> None:
    """Configure logging for chat mode to reduce noise from external libraries."""
    # This is now handled in ChatSession._setup_logging()
    pass


def start_chat(
    model: str = "openai",
    session_id: Optional[str] = None,
    account: Optional[str] = None,
) -> None:
    """
    Start an interactive chat session with beautiful UI.

    Args:
        model (str): Model key to use (gemini, openai, anthropic).
        session_id (str, optional): Session ID for persistent conversation history.
        account (str, optional): Account name to use for database access.
    """
    try:
        session = ChatSession(model_key=model, session_id=session_id, account=account)
        session.start_interactive()
    except Exception as e:
        print(f"❌ Failed to start chat: {e}")
        logger.error(f"Failed to start chat: {e}")


def ask_single_question(
    question: str,
    model: str = "openai",
    session_id: Optional[str] = None,
    account: Optional[str] = None,
) -> str:
    """
    Ask a single question to the agent without starting interactive chat.

    Args:
        question (str): The question to ask.
        model (str): Model key to use (gemini, openai, anthropic).
        session_id (str, optional): Session ID for persistent conversation history.
        account (str, optional): Account name to use for database access.

    Returns:
        str: The agent's response.
    """
    try:
        session = ChatSession(model_key=model, session_id=session_id, account=account)
        return session.ask_question(question, model)
    except Exception as e:
        return f"❌ Error: {e}"


# Backward compatibility functions
def get_model_name(model_key: str) -> str:
    """Get the full model name from a simple key (backward compatibility)."""
    try:
        config = ModelManager.get_model_config(model_key)
        return config.full_identifier
    except:
        return ModelManager.get_model_config("openai").full_identifier


def show_model_options() -> str:
    """Display available models and let user choose (backward compatibility)."""
    from .ui import ChatDisplay

    display = ChatDisplay()
    return display.show_model_selection(ModelManager.MODEL_SELECTION)


# Legacy exports for backward compatibility
MODEL_MAP = {
    "gemini": "gemini/gemini-2.0-flash-exp",
    "openai": "openai/gpt-4.1",
    "anthropic": "anthropic/claude-3-5-sonnet-20241022",
}

MODEL_DESCRIPTIONS = {
    "gemini": "Gemini 2.0 Flash Exp (Latest & Advanced)",
    "openai": "OpenAI GPT-4.1 (Latest & Most Capable)",
    "anthropic": "Claude 3.5 Sonnet (Most Capable)",
}

# Re-export for compatibility
ChatError = ChatError

# Import the old classes for backward compatibility if needed
try:
    from .agents.email_analyst import EmailAnalysisAgent
    from .agents.tools import EnhancedSQLiteTool
except ImportError:
    # Fallback to a simple implementation if the new modules aren't available
    class EmailAnalysisAgent:
        def __init__(self, *args, **kwargs):
            raise NotImplementedError("New modular implementation not available")

    class EnhancedSQLiteTool:
        def __init__(self, *args, **kwargs):
            raise NotImplementedError("New modular implementation not available")
