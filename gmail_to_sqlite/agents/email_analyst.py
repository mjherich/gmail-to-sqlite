"""Main email analysis agent with LangChain integration and beautiful UI."""

import sqlite3
import uuid
import logging
from typing import Optional, Dict, Any, Callable

from crewai import Agent, Task, Crew, Process
from crewai.tools import BaseTool
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.runnables.base import Runnable
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_community.chat_message_histories import SQLChatMessageHistory

from ..core.models import ModelManager
from ..core.errors import ChatError
from ..tools import EmailPatternAnalyzer
from .tools import EnhancedSQLiteTool
from ..ui import ChatDisplay


logger = logging.getLogger(__name__)


class CrewAIRunnable(Runnable):
    """LangChain Runnable wrapper for CrewAI agents with UI integration."""

    def __init__(
        self, 
        crew_agent: Agent, 
        db_path: str, 
        llm: Any,
        display_callback: Optional[Callable] = None
    ):
        """Initialize the runnable wrapper."""
        self.crew_agent = crew_agent
        self.db_path = db_path
        self.llm = llm
        self.display_callback = display_callback
        self.sqlite_tool = None
        self.pattern_analyzer = None

    def set_tools(self, sqlite_tool: Any, pattern_analyzer: Any) -> None:
        """Set the tools for the agent."""
        self.sqlite_tool = sqlite_tool
        self.pattern_analyzer = pattern_analyzer

    def invoke(
        self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None
    ) -> str:
        """Invoke the CrewAI agent with LangChain-compatible interface."""
        try:
            user_message = input_data.get("input", "")
            if not user_message:
                return "No input provided."

            # Create a task for the CrewAI agent following best practices
            task_description = f"""
            Current user message: {user_message}
            
            Instructions for Gmail Data Analysis:
            1. Respond naturally and conversationally to the user's question
            2. For data analysis questions, use the Enhanced SQLite Query Tool strategically
            3. When using the SQLite tool, you can pass natural language questions or SQL queries
            4. For pattern analysis beyond basic SQL, use the Email Pattern Analyzer tool
            5. Always provide clear insights and context for query results
            6. Explain what the data means and why it's interesting
            7. Suggest follow-up questions when appropriate
            8. Be helpful, informative, and maintain conversation context
            
            Your Expertise: You are a Gmail data analysis expert with deep knowledge of:
            - Email communication patterns and trends
            - Productivity insights from email behavior
            - SQL optimization for email data queries
            - Statistical analysis of communication metrics
            
            Response Style: Professional yet conversational, always explaining insights clearly.
            """

            task = Task(
                description=task_description,
                expected_output="A helpful, insightful response that addresses the user's question about their Gmail data. Include data analysis results when requested, with clear explanations and context.",
                agent=self.crew_agent,
            )

            # Create a crew with just this agent and task
            crew = Crew(
                agents=[self.crew_agent],
                tasks=[task],
                process=Process.sequential,
                verbose=False,
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
            # Handle specific error types with user-friendly messages
            error_type = type(e).__name__

            if "RateLimitError" in error_type:
                return "⏳ Rate limit reached. Please wait a moment and try again."
            elif "AuthenticationError" in error_type:
                return "🔐 Authentication failed. Please check your API keys in .secrets.toml"
            elif "NotFoundError" in error_type:
                return "🔍 Model not found. Try switching to a different model."
            else:
                return f"Error processing your message: {e}"


class EmailAnalysisAgent:
    """Enhanced CrewAI agent specialized in email data analysis with modern UI."""

    def __init__(
        self,
        db_path: str,
        model_key: str = "openai",
        session_id: Optional[str] = None,
        display_callback: Optional[Callable] = None,
    ):
        """Initialize the email analysis agent."""
        self.db_path = db_path
        self.model_key = model_key
        self.session_id = session_id or str(uuid.uuid4())
        self.display_callback = display_callback

        # Initialize persistent conversation history
        self.chat_history = self._get_session_history(self.session_id)

        # Create the LLM instance using ModelManager
        self.llm = ModelManager.create_llm(model_key)

        # Initialize tools with display callback
        self.sqlite_tool = EnhancedSQLiteTool(
            db_path=db_path, 
            llm=self.llm,
            display_callback=display_callback
        )
        self.pattern_analyzer = EmailPatternAnalyzer(db_path=db_path)

        # Get database schema for context
        self.db_schema = self._get_database_schema()

        # Create the enhanced CrewAI agent following best practices
        self.agent = Agent(
            role="Gmail Data Analysis Specialist",
            goal="Provide deep, actionable insights about Gmail data through intelligent analysis and natural conversation, focusing on communication patterns, productivity metrics, and email behavior trends",
            backstory=f"""You are a world-class email analytics specialist with 15+ years of experience in:

📊 **Communication Analytics**: Expert in analyzing email patterns, volume trends, response times, and interaction networks to uncover meaningful insights about digital communication behavior.

🔍 **Data Intelligence**: Advanced skills in SQL optimization, statistical analysis, and pattern recognition specifically for email datasets. You excel at translating complex queries into actionable business intelligence.

💡 **Productivity Consulting**: Deep understanding of how email patterns reflect work habits, relationship dynamics, and organizational communication flows. You provide strategic recommendations based on data insights.

🧠 **Contextual Analysis**: Strong ability to maintain conversation context, remember previous analyses, and build upon past insights to provide increasingly sophisticated recommendations.

**Your Database Expertise**: 
{self.db_schema}

**Your Analytical Approach**:
- Always explain what you're analyzing and why it's valuable
- Provide context and interpretation, not just raw data
- Suggest follow-up analyses and interesting questions
- Connect findings to productivity and communication best practices
- Use sophisticated SQL when needed, but explain insights in plain language
- Maintain conversation continuity and build upon previous discussions

**Your Communication Style**: Professional yet approachable, focusing on actionable insights rather than technical jargon. You help users understand their digital communication patterns to improve productivity and relationships.""",
            llm=self.llm,
            verbose=False,
            memory=True,  # Enhanced persistent memory
            respect_context_window=True,  # Auto-manage context limits
            allow_delegation=False,
            max_rpm=30,  # Rate limiting for cost control
            function_calling_llm=self.llm,
            tools=[self.sqlite_tool, self.pattern_analyzer],
        )

        # Create LangChain-compatible runnable wrapper
        self.agent_runnable = CrewAIRunnable(
            self.agent, db_path, self.llm, display_callback
        )
        self.agent_runnable.set_tools(self.sqlite_tool, self.pattern_analyzer)

        # Wrap with RunnableWithMessageHistory for enhanced message handling
        self.agent_with_history = RunnableWithMessageHistory(
            self.agent_runnable,
            lambda session_id: self._get_session_history(session_id),
            input_messages_key="input",
            history_messages_key="chat_history",
        )

    def _get_session_history(self, session_id: str) -> SQLChatMessageHistory:
        """Get or create a SQLChatMessageHistory for the given session."""
        connection_string = f"sqlite:///{self.db_path}"
        return SQLChatMessageHistory(
            session_id=session_id,
            connection=connection_string,
            table_name="chat_message_store",  # Different table from messages
        )

    def _get_database_schema(self) -> str:
        """Extract the database schema for context."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            schema_parts = []

            # Get all table names
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()

            for table in tables:
                table_name = table[0]
                if table_name == "chat_message_store":
                    continue  # Skip chat history table
                    
                schema_parts.append(f"Table: {table_name}")

                # Get column information
                cursor.execute(f"PRAGMA table_info({table_name});")
                columns = cursor.fetchall()

                schema_parts.append("Columns:")
                for col in columns:
                    col_name, col_type = col[1], col[2]
                    schema_parts.append(f"  - {col_name}: {col_type}")

                schema_parts.append("")  # Empty line between tables

            conn.close()
            return "\n".join(schema_parts)

        except Exception as e:
            logger.warning(f"Could not read database schema: {e}")
            return "Database schema not available"

    def chat(self, user_message: str) -> str:
        """Process a user message and return the agent's response."""
        try:
            # Use RunnableWithMessageHistory for enhanced message handling
            response = self.agent_with_history.invoke(
                {"input": user_message},
                config={"configurable": {"session_id": self.session_id}},
            )

            return response

        except Exception as e:
            import traceback

            # Handle specific error types
            error_type = type(e).__name__

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
            else:
                # Generic error handling
                error_msg = f"Error processing your message: {e}"
                detailed_error = (
                    f"Error details: {str(e)}\nTraceback: {traceback.format_exc()}"
                )
                logger.error(detailed_error)

                return error_msg