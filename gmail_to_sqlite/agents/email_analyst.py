"""Gmail Q&A Agent - A friendly AI assistant for analyzing Gmail data."""

import os
import sqlite3
import uuid
import logging
from typing import Optional, Callable

from crewai import Agent, Task, Crew, Process

from ..core.models import ModelManager
from ..core.errors import ErrorHandler
from .tools import EnhancedSQLiteTool
from ..config import get_primary_account_config, settings


logger = logging.getLogger(__name__)


class EmailAnalysisAgent:
    """A friendly AI assistant that helps you understand your Gmail data through natural conversation."""

    def __init__(
        self,
        db_path: str,
        model_key: str = "openai",
        session_id: Optional[str] = None,
        display_callback: Optional[Callable] = None,
    ):
        """Initialize the Gmail Q&A agent."""
        self.db_path = db_path
        self.model_key = model_key
        self.session_id = session_id or str(uuid.uuid4())
        self.display_callback = display_callback

        # Load user configuration for personalization
        self.user_config = get_primary_account_config()

        # Create the LLM instance using ModelManager
        self.llm = ModelManager.create_llm(model_key)

        # Set environment variable for CrewAI (required in newer versions)
        config = ModelManager.get_model_config(model_key)
        api_key = settings.get(config.api_key_name)
        if api_key:
            os.environ[config.api_key_name] = api_key

        # Initialize SQL tool for database queries
        self.sql_tool = EnhancedSQLiteTool(
            db_path=db_path,
            llm=self.llm,
            display_callback=display_callback,
            max_rows=500,  # Reasonable limit for better performance
            max_field_length=1000,  # Reasonable field length limit
        )

        # Get database schema for context
        self.db_schema = self._get_database_schema()

        # Create the human-like CrewAI agent
        self.agent = Agent(
            role="Gmail Assistant",
            goal="Help users understand their Gmail data by answering questions in a friendly, conversational way using SQL queries to find the information they need.",
            backstory=self._build_backstory(),
            llm=self.llm,
            verbose=False,
            memory=True,
            allow_delegation=False,
            tools=[self.sql_tool],
        )

    def _build_backstory(self) -> str:
        """Build a human-like backstory for the agent."""
        user_name = (
            self.user_config.get("name", "friend") if self.user_config else "friend"
        )

        return f"""You are a helpful Gmail assistant who loves helping people understand their email data. 
        
You're chatting with {user_name}, and your job is to answer their questions about their Gmail inbox in a friendly, conversational way. 

When they ask about their emails, you:
- Use your SQL tool to query their Gmail database
- Explain what you found in plain English
- Provide insights and context about their email patterns
- Keep the conversation natural and engaging

Your database contains their Gmail messages with details like:
- Senders and recipients
- Subject lines and message content
- Labels (like "Action Item", "Important", etc.)
- Timestamps and read status
- Thread information

You're knowledgeable about email data but always explain things clearly, as if you're a friend helping them explore their inbox.

Database Schema:
{self.db_schema}
"""

    def _get_database_schema(self) -> str:
        """Extract the database schema for context."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Get the messages table structure
            cursor.execute("PRAGMA table_info(messages);")
            columns = cursor.fetchall()

            schema_info = "Messages table columns:\n"
            for col in columns:
                col_name, col_type = col[1], col[2]
                schema_info += f"- {col_name}: {col_type}\n"

            # Get sample data to understand the structure
            cursor.execute("SELECT COUNT(*) FROM messages")
            total_count = cursor.fetchone()[0]
            schema_info += f"\nTotal messages: {total_count}"

            conn.close()
            return schema_info

        except Exception as e:
            logger.warning(f"Could not read database schema: {e}")
            return "Database schema not available"

    def chat(self, user_message: str) -> str:
        """Process a user message and return a friendly response."""
        try:
            # Create a simple, focused task
            task = Task(
                description=f"""
                The user asked: "{user_message}"
                
                Help them by:
                1. Understanding what they want to know about their Gmail data
                2. Using the Enhanced SQLite Query Tool to find the information
                3. Explaining the results in a friendly, conversational way
                4. Providing any relevant insights or context
                
                Be natural and helpful - like a friend who's good with data helping them explore their email.
                """,
                expected_output="A friendly, helpful response that answers the user's question about their Gmail data with clear explanations and insights.",
                agent=self.agent,
            )

            # Create a simple crew with just this agent and task
            crew = Crew(
                agents=[self.agent],
                tasks=[task],
                process=Process.sequential,
                verbose=False,
                memory=True,
            )

            # Execute the task with retry logic
            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    if attempt > 0:
                        import time

                        time.sleep(2)  # Brief pause between retries

                    result = crew.kickoff()
                    break
                except Exception as crew_error:
                    error_type = type(crew_error).__name__
                    if "RateLimitError" in error_type and attempt < max_retries:
                        continue
                    else:
                        raise crew_error

            # Extract the response
            response = str(result.raw) if hasattr(result, "raw") else str(result)
            return response

        except Exception as e:
            import traceback

            # Log detailed error for debugging
            detailed_error = (
                f"Error details: {str(e)}\nTraceback: {traceback.format_exc()}"
            )
            logger.error(detailed_error)

            # Use centralized error handler for user-friendly messages
            if "database" in str(e).lower() or "sqlite" in str(e).lower():
                return ErrorHandler.handle_database_error(e)
            elif "configuration" in str(e).lower() or "config" in str(e).lower():
                return ErrorHandler.handle_configuration_error(e)
            else:
                return ErrorHandler.handle_api_error(e)
