"""Chat session management and orchestration."""

import os
import uuid
import logging
from typing import Optional

from ..constants import DATABASE_FILE_NAME
from ..config import settings, get_primary_account_config, get_user_config
from ..ui import ChatDisplay
from .models import ModelManager
from .errors import ChatError, DatabaseError
from ..agents.email_analyst import EmailAnalysisAgent


logger = logging.getLogger(__name__)


class ChatSession:
    """Manages a complete chat session with proper separation of concerns."""

    def __init__(
        self,
        model_key: Optional[str] = None,
        session_id: Optional[str] = None,
        display_width: Optional[int] = None,
        account: Optional[str] = None,
    ):
        """Initialize a chat session."""
        self.session_id = session_id or str(uuid.uuid4())
        self.display = ChatDisplay(width=display_width)
        self.agent: Optional[EmailAnalysisAgent] = None
        self.current_model_key = model_key
        self.account = account
        self._setup_logging()

    def _setup_logging(self):
        """Configure logging for chat mode to reduce noise."""
        # Suppress verbose logging from external libraries
        external_loggers = [
            "LiteLLM",
            "litellm",
            "httpx",
            "httpcore",
            "crewai",
            "langchain",
            "openai",
            "anthropic",
            "google",
        ]

        for logger_name in external_loggers:
            logging.getLogger(logger_name).setLevel(logging.WARNING)

        # Keep our own logger at INFO level
        logging.getLogger("gmail_to_sqlite").setLevel(logging.INFO)

    def _get_database_path(self) -> str:
        """Get the database path from configuration."""
        try:
            if self.account:
                account_config = get_user_config(self.account)
                if not account_config:
                    raise ChatError(
                        f"Account '{self.account}' not found in configuration"
                    )
            else:
                account_config = get_primary_account_config()

            data_dir = account_config["data_dir"]
        except (ValueError, KeyError) as e:
            raise ChatError(f"Account configuration error: {e}")

        if not data_dir:
            account_name = self.account or "primary account"
            raise ChatError(f"data_dir not configured for {account_name}")

        db_path = f"{data_dir}/{DATABASE_FILE_NAME}"

        if not os.path.exists(db_path):
            raise DatabaseError(
                f"Database not found at {db_path}",
                db_path=db_path,
                suggestion="Please sync your Gmail data first using: gmail-to-sqlite sync",
            )

        return db_path

    def _select_model(self) -> str:
        """Select the AI model to use."""
        if self.current_model_key:
            # Validate the provided model
            if not ModelManager.validate_model_key(self.current_model_key):
                self.display.show_error(
                    f"Invalid model: {self.current_model_key}", "Model Selection"
                )
                self.current_model_key = None
            else:
                return self.current_model_key

        # Show model selection UI
        return self.display.show_model_selection(ModelManager.MODEL_SELECTION)

    def _initialize_agent(self, model_key: str) -> EmailAnalysisAgent:
        """Initialize the analysis agent with the selected model."""
        db_path = self._get_database_path()

        try:
            with self.display.show_processing("Initializing agent"):
                # Create a display callback function
                def display_callback(method_name: str, *args, **kwargs):
                    if hasattr(self.display, method_name):
                        method = getattr(self.display, method_name)
                        return method(*args, **kwargs)

                agent = EmailAnalysisAgent(
                    db_path=db_path,
                    model_key=model_key,
                    session_id=self.session_id,
                    display_callback=display_callback,
                )

            model_description = ModelManager.get_model_description(model_key)
            self.display.show_initialization(model_description, self.session_id)

            return agent

        except Exception as e:
            # Convert to appropriate error type
            if "API" in str(e) or "key" in str(e).lower():
                self.display.show_error(str(e), "Configuration Error")
            else:
                self.display.show_error(
                    f"Failed to initialize agent: {e}", "Initialization Error"
                )
            raise

    def start_interactive(self) -> None:
        """Start an interactive chat session."""
        try:
            # Model selection
            model_key = self._select_model()
            self.current_model_key = model_key

            # Initialize agent
            self.agent = self._initialize_agent(model_key)

            # Show welcome screen
            model_description = ModelManager.get_model_description(model_key)
            self.display.show_welcome(model_description)

            # Main chat loop
            self._chat_loop()

        except (ChatError, DatabaseError) as e:
            self.display.show_error(str(e))
            if e.suggestion:
                self.display.show_info(e.suggestion, "Suggestion")
        except Exception as e:
            self.display.show_error(f"Unexpected error: {e}", "System Error")
            logger.error(f"Unexpected error in chat session: {e}")

    def _chat_loop(self) -> None:
        """Main interactive chat loop."""
        while True:
            try:
                # Get user input
                user_input = self.display.show_user_input().strip()

                # Handle special commands
                if user_input.lower() in ["exit", "quit", "bye"]:
                    self.display.show_goodbye()
                    break

                if user_input.lower() == "model":
                    self._handle_model_switch()
                    continue

                if not user_input:
                    continue

                # Process the message
                self._process_message(user_input)

            except KeyboardInterrupt:
                self.display.show_goodbye()
                break
            except EOFError:
                self.display.show_goodbye()
                break
            except Exception as e:
                self.display.show_error(f"Error processing message: {e}")

    def _handle_model_switch(self) -> None:
        """Handle switching AI models."""
        try:
            new_model_key = self.display.show_model_selection(
                ModelManager.MODEL_SELECTION
            )

            if new_model_key == self.current_model_key:
                self.display.show_info("Already using this model", "Model Switch")
                return

            # Initialize new agent with same session
            self.agent = self._initialize_agent(new_model_key)
            self.current_model_key = new_model_key

            model_description = ModelManager.get_model_description(new_model_key)
            self.display.show_success(
                f"Switched to {model_description}", "Model Switch"
            )

        except Exception as e:
            self.display.show_error(f"Failed to switch model: {e}", "Model Switch")

    def _process_message(self, user_input: str) -> None:
        """Process a user message and show the response."""
        if not self.agent:
            self.display.show_error("Agent not initialized", "System Error")
            return

        try:
            with self.display.show_processing("Processing your question"):
                response = self.agent.chat(user_input)

            self.display.show_agent_response(response)

        except Exception as e:
            # Handle specific error types with user-friendly messages
            error_type = type(e).__name__

            if "RateLimitError" in error_type:
                self.display.show_warning(
                    "Rate limit reached. Please wait a moment and try again.",
                    "Rate Limit",
                )
            elif "AuthenticationError" in error_type:
                self.display.show_error(
                    "Authentication failed. Please check your API keys in .secrets.toml",
                    "Authentication",
                )
            elif "NotFoundError" in error_type:
                self.display.show_error(
                    "Model not found. Try switching to a different model using 'model' command.",
                    "Model Error",
                )
            else:
                self.display.show_error(f"Error processing message: {e}")

    def ask_question(self, question: str, model_key: Optional[str] = None) -> str:
        """Ask a single question without starting interactive mode."""
        try:
            # Use provided model or current model or default
            selected_model = model_key or self.current_model_key or "openai"

            if not ModelManager.validate_model_key(selected_model):
                return f"❌ Invalid model: {selected_model}"

            # Initialize agent if needed
            if not self.agent or self.current_model_key != selected_model:
                self.agent = self._initialize_agent(selected_model)
                self.current_model_key = selected_model

            # Process the question
            return self.agent.chat(question)

        except (ChatError, DatabaseError) as e:
            return f"❌ {e}"
        except Exception as e:
            return f"❌ Error: {e}"
