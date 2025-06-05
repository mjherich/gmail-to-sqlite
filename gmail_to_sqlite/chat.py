"""
Multi-turn chat interface using AI agents for Gmail data analysis.

This module provides an interactive chat CLI where users can have ongoing
conversations with AI agents specialized in analyzing Gmail data.
"""

import logging
import os
import sqlite3
import sys
from typing import List, Optional

from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import BaseTool

from .constants import DATABASE_FILE_NAME
from .config import settings


logger = logging.getLogger(__name__)


# Model mapping from simple names to full model identifiers
MODEL_MAP = {
    "gemini": "gemini/gemini-2.0-flash-exp",
    "openai": "openai/gpt-4o",
    "claude": "anthropic/claude-4-sonnet-2024-05-22",
}

# Model descriptions for display
MODEL_DESCRIPTIONS = {
    "gemini": "Gemini 2.0 Flash (Fast & Cheap)",
    "openai": "OpenAI GPT-4o (Balanced)",
    "claude": "Claude 4 Sonnet (Most Capable)",
}


class ChatError(Exception):
    """Custom exception for chat-related errors."""

    pass


def setup_chat_logging() -> None:
    """Configure logging for chat mode to reduce noise from LiteLLM and other libraries."""
    # Suppress verbose logging from external libraries
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    logging.getLogger("litellm").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("crewai").setLevel(logging.WARNING)
    logging.getLogger("langchain").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)

    # Keep our own logger at INFO level
    logging.getLogger("gmail_to_sqlite").setLevel(logging.INFO)


class SQLiteTool(BaseTool):
    """A custom CrewAI tool for executing SQL queries against SQLite databases."""

    name: str = "SQLite Query Tool"
    description: str = """
    Execute SQL queries against a SQLite database containing Gmail messages.
    
    Input should be a natural language question about email data, and the tool will:
    1. Convert it to an appropriate SQL query
    2. Execute the query against the database
    3. Return formatted results
    
    The database contains a 'messages' table with these columns:
    - message_id: Unique Gmail message ID  
    - thread_id: Gmail thread ID
    - sender: JSON with sender name and email
    - recipients: JSON with to/cc/bcc recipients
    - labels: JSON array of Gmail labels
    - subject: Email subject line
    - body: Email body content (plain text)
    - size: Message size in bytes
    - timestamp: When the message was sent/received
    - is_read: Boolean if message is read
    - is_outgoing: Boolean if sent by user
    - is_deleted: Boolean if deleted from Gmail
    - last_indexed: When message was last synced
    
    Examples:
    - "Who sends me the most emails?" -> SELECT sender->>'$.email', COUNT(*) FROM messages GROUP BY sender->>'$.email' ORDER BY COUNT(*) DESC
    - "How many unread emails do I have?" -> SELECT COUNT(*) FROM messages WHERE is_read = 0
    - "Show me emails from last week" -> SELECT subject, sender FROM messages WHERE timestamp >= date('now', '-7 days')
    """

    def __init__(self, db_path: str, **kwargs):
        super().__init__(**kwargs)
        self._db_path = db_path

    def _run(self, query: str) -> str:
        """
        Execute a SQL query or convert natural language to SQL and execute it.

        Args:
            query: Either a natural language question or SQL query

        Returns:
            Formatted query results
        """
        try:
            # If it's already a SQL query (starts with SELECT, INSERT, etc.), execute directly
            query_upper = query.strip().upper()
            if any(
                query_upper.startswith(cmd)
                for cmd in ["SELECT", "INSERT", "UPDATE", "DELETE", "WITH"]
            ):
                sql_query = query
                print(
                    f"🔍 Executing SQL: {sql_query[:100]}{'...' if len(sql_query) > 100 else ''}"
                )
            else:
                # Convert natural language to SQL
                sql_query = self._natural_language_to_sql(query)
                print(f"🔄 Converted '{query}' to SQL:")
                print(f"   {sql_query}")

            # Execute the query
            result = self._execute_sql_query(sql_query)

            lines = result.split("\n")
            result_preview = "\n".join(lines[:5])
            if len(lines) > 5:
                result_preview += f"\n   ... ({len(lines) - 5} more lines)"
            print(f"📊 Query returned: {result_preview}")

            return result

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            print(f"❌ SQL Error: {error_msg}")
            return error_msg

    def _natural_language_to_sql(self, question: str) -> str:
        """
        Convert natural language questions to SQL queries.

        This is a simple pattern-matching approach. For more complex queries,
        you could integrate with an LLM here.
        """
        question_lower = question.lower()

        # Extract year filters if present
        year_filter = ""
        for year in range(2000, 2030):
            if str(year) in question_lower:
                year_filter = f" AND strftime('%Y', timestamp) = '{year}'"
                break

        # Common patterns
        if (
            "who sends me the most emails" in question_lower
            or "top senders" in question_lower
        ):
            return f"""
            SELECT sender->>'$.email' as sender_email, 
                   sender->>'$.name' as sender_name,
                   COUNT(*) as email_count
            FROM messages 
            WHERE is_outgoing = 0{year_filter}
            GROUP BY sender->>'$.email', sender->>'$.name'
            ORDER BY email_count DESC 
            LIMIT 10
            """

        elif "unread" in question_lower:
            return f"SELECT COUNT(*) as unread_count FROM messages WHERE is_read = 0{year_filter}"

        elif "last week" in question_lower or "past week" in question_lower:
            return f"""
            SELECT subject, sender->>'$.email' as sender, timestamp
            FROM messages 
            WHERE timestamp >= date('now', '-7 days'){year_filter}
            ORDER BY timestamp DESC
            LIMIT 20
            """

        elif "last month" in question_lower or "past month" in question_lower:
            return f"""
            SELECT subject, sender->>'$.email' as sender, timestamp
            FROM messages 
            WHERE timestamp >= date('now', '-30 days'){year_filter}
            ORDER BY timestamp DESC
            LIMIT 20
            """

        elif "today" in question_lower:
            return f"""
            SELECT subject, sender->>'$.email' as sender, timestamp
            FROM messages 
            WHERE date(timestamp) = date('now'){year_filter}
            ORDER BY timestamp DESC
            """

        elif "labels" in question_lower and (
            "most common" in question_lower or "frequent" in question_lower
        ):
            return f"""
            SELECT json_extract(label.value, '$') as label_name, COUNT(*) as count
            FROM messages, json_each(messages.labels) as label
            WHERE 1=1{year_filter}
            GROUP BY label_name
            ORDER BY count DESC
            LIMIT 10
            """

        elif "total" in question_lower and "emails" in question_lower:
            return (
                f"SELECT COUNT(*) as total_emails FROM messages WHERE 1=1{year_filter}"
            )

        elif "sent" in question_lower and (
            "by me" in question_lower or "outgoing" in question_lower
        ):
            return f"SELECT COUNT(*) as sent_emails FROM messages WHERE is_outgoing = 1{year_filter}"

        elif "received" in question_lower or "incoming" in question_lower:
            return f"SELECT COUNT(*) as received_emails FROM messages WHERE is_outgoing = 0{year_filter}"

        elif "largest" in question_lower and "emails" in question_lower:
            return f"""
            SELECT subject, sender->>'$.email' as sender, size, timestamp
            FROM messages 
            WHERE 1=1{year_filter}
            ORDER BY size DESC
            LIMIT 10
            """

        else:
            # Default: return a helpful query showing recent emails
            return f"""
            SELECT subject, sender->>'$.email' as sender, timestamp, is_read
            FROM messages 
            WHERE 1=1{year_filter}
            ORDER BY timestamp DESC
            LIMIT 10
            """

    def _execute_sql_query(self, sql_query: str) -> str:
        """Execute a SQL query and return formatted results."""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()

            cursor.execute(sql_query)
            results = cursor.fetchall()

            # Get column names
            column_names = (
                [description[0] for description in cursor.description]
                if cursor.description
                else []
            )

            conn.close()

            if not results:
                return "No results found."

            # Format results as a simple table
            if column_names:
                result_lines = [" | ".join(column_names)]
                result_lines.append("-" * len(result_lines[0]))

                for row in results[:20]:  # Limit to 20 rows for readability
                    formatted_row = []
                    for value in row:
                        if value is None:
                            formatted_row.append("NULL")
                        else:
                            str_value = str(value)
                            # Truncate long values
                            if len(str_value) > 50:
                                str_value = str_value[:47] + "..."
                            formatted_row.append(str_value)
                    result_lines.append(" | ".join(formatted_row))

                if len(results) > 20:
                    result_lines.append(
                        f"... ({len(results)} total rows, showing first 20)"
                    )

                return "\n".join(result_lines)
            else:
                return f"Query executed successfully. {len(results)} rows affected."

        except Exception as e:
            return f"SQL Error: {e}"


class EmailAnalysisAgent:
    """CrewAI agent specialized in email data analysis."""

    def __init__(
        self,
        db_path: str,
        model_name: str = "gemini/gemini-2.0-flash-exp",
    ):
        """
        Initialize the email analysis agent.

        Args:
            db_path (str): Path to the SQLite database file.
            model_name (str): The LLM model to use.
        """
        self.db_path = db_path
        self.conversation_history: List[str] = []
        self.model_name = model_name

        # Initialize LLM based on model choice
        if model_name.startswith("gemini/"):
            api_key = settings.get("GOOGLE_API_KEY")
            if not api_key:
                raise ChatError(
                    "Google API key not found. Please set the GOOGLE_API_KEY in .secrets.toml.\n\n"
                    "Configuration:\n"
                    'Add to .secrets.toml: GOOGLE_API_KEY = "your-key-here"\n\n'
                    "Get your API key from: https://aistudio.google.com/app/apikey"
                )
        elif model_name.startswith("openai/"):
            api_key = settings.get("OPENAI_API_KEY")
            if not api_key:
                raise ChatError(
                    "OpenAI API key not found. Please set the OPENAI_API_KEY in .secrets.toml.\n\n"
                    "Configuration:\n"
                    'Add to .secrets.toml: OPENAI_API_KEY = "your-key-here"\n\n'
                    "Get your API key from: https://platform.openai.com/api-keys"
                )
        elif model_name.startswith("anthropic/"):
            api_key = settings.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise ChatError(
                    "Anthropic API key not found. Please set the ANTHROPIC_API_KEY in .secrets.toml.\n\n"
                    "Configuration:\n"
                    'Add to .secrets.toml: ANTHROPIC_API_KEY = "your-key-here"\n\n'
                    "Get your API key from: https://console.anthropic.com/"
                )
        else:
            raise ChatError(f"Unsupported model: {model_name}")

        # Create the LLM instance for CrewAI
        self.llm = LLM(model=model_name, api_key=api_key, temperature=0.1)

        # Initialize the custom SQLite tool
        self.sqlite_tool = SQLiteTool(db_path=db_path)

        # Get database schema for context
        self.db_schema = self._get_database_schema()

        # Create the CrewAI agent with the SQLite tool
        self.agent = Agent(
            role="Gmail Data Analyst",
            goal="Help users analyze and understand their Gmail data through natural conversation and SQL queries",
            backstory=f"""You are an expert data analyst specializing in email data analysis. 
            You have access to a SQLite database containing Gmail messages with the following schema:
            
            {self.db_schema}
            
            You can:
            - Answer questions about email patterns, senders, recipients, and content
            - Execute SQL queries using the SQLite Query Tool to extract specific information
            - Provide insights and analytics about email usage
            - Maintain context across multiple conversation turns
            
            When users ask questions about their email data, use the SQLite Query Tool to query the database
            and provide accurate results. Always explain what you're analyzing and provide clear insights
            based on the results. You can pass either natural language questions or SQL queries to the tool.""",
            llm=self.llm,
            verbose=False,
            memory=True,
            allow_delegation=False,
            tools=[self.sqlite_tool],
        )

    def _get_database_schema(self) -> str:
        """
        Extract the database schema for context.

        Returns:
            str: A formatted string describing the database schema.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            schema_parts = []

            # Get all table names
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()

            for table in tables:
                table_name = table[0]
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
        """
        Process a user message and return the agent's response.

        Args:
            user_message (str): The user's message.

        Returns:
            str: The agent's response.
        """
        try:
            # Show progress indicator
            print(f"🤔 Processing your question...")

            # Add user message to conversation history
            self.conversation_history.append(f"User: {user_message}")

            # Create context with conversation history
            context = "\n".join(
                self.conversation_history[-10:]
            )  # Keep last 10 exchanges

            # Create a task for the agent
            task_description = f"""
            Conversation context:
            {context}
            
            Current user message: {user_message}
            
            Instructions:
            1. Respond naturally to the user's question or request
            2. If they're asking for data analysis, use the SQLite Query Tool to query the database
            3. When using the SQLite Query Tool, you can pass either natural language questions or SQL queries
            4. Provide clear insights based on the query results
            5. If they're asking about email patterns, provide helpful analysis
            6. Maintain conversational flow and reference previous context when relevant
            7. Be helpful and informative
            
            Remember: You have access to a SQLite database containing Gmail messages. Use the SQLite Query Tool
            to answer questions that require querying the database.
            """

            task = Task(
                description=task_description,
                expected_output="A helpful, conversational response that addresses the user's question about their Gmail data, including any query results if data analysis was requested.",
                agent=self.agent,
            )

            # Create a crew with just this agent and task
            crew = Crew(
                agents=[self.agent],
                tasks=[task],
                process=Process.sequential,
                verbose=False,
            )

            # Execute the task
            result = crew.kickoff()

            # Extract the response
            response = str(result.raw) if hasattr(result, "raw") else str(result)

            # Add agent response to conversation history
            self.conversation_history.append(f"Assistant: {response}")

            return response

        except Exception as e:
            error_msg = f"Error processing your message: {e}"
            logger.error(error_msg)
            return error_msg


def get_model_name(model_key: str) -> str:
    """
    Get the full model name from a simple key.

    Args:
        model_key (str): Simple model key (gemini, openai, claude)

    Returns:
        str: Full model identifier
    """
    return MODEL_MAP.get(model_key, MODEL_MAP["gemini"])


def show_model_options() -> str:
    """
    Display available models and let user choose.
    Used only when no model is specified via CLI.

    Returns:
        str: The selected model name.
    """
    models = {
        "1": ("gemini", "Gemini 2.0 Flash (Default - Fast & Cheap)"),
        "2": ("openai", "OpenAI GPT-4o (Balanced)"),
        "3": ("claude", "Claude 3.5 Sonnet (Most Capable)"),
    }

    print("\n🤖 Available AI Models:")
    for key, (model_key, description) in models.items():
        print(f"   {key}. {description}")

    while True:
        choice = input("\nSelect model (1-3) or press Enter for default: ").strip()

        if not choice:  # Default
            return get_model_name("gemini")

        if choice in models:
            selected_model_key = models[choice][0]
            print(f"✅ Selected: {models[choice][1]}")
            return get_model_name(selected_model_key)

        print("❌ Invalid choice. Please select 1, 2, or 3.")


def start_chat(model: str = "gemini") -> None:
    """
    Start an interactive chat session with the email analysis agent.
    Uses data directory from settings.

    Args:
        model (str): Model key to use (gemini, openai, claude).
    """
    # Configure chat-specific logging
    setup_chat_logging()

    data_dir = settings.get("DATA_DIR")
    if not data_dir:
        raise ChatError("DATA_DIR not configured in settings")

    db_path = f"{data_dir}/{DATABASE_FILE_NAME}"

    # Check if database exists
    if not os.path.exists(db_path):
        print(f"❌ Database not found at {db_path}")
        print("Please sync your Gmail data first using: gmail-to-sqlite sync")
        return

    try:
        # Get the full model name
        model_name = get_model_name(model)
        model_description = MODEL_DESCRIPTIONS.get(model, "Unknown Model")

        print(f"🤖 Using {model_description}")
        print("✅ Tool usage enabled - you'll see SQL queries and results")

        # Initialize the agent with selected model
        print(f"\n🤖 Initializing Gmail Analysis Agent...")
        agent = EmailAnalysisAgent(db_path, model_name=model_name)

        print("✅ Agent ready! You can now chat about your Gmail data.")
        print("💡 Try asking things like:")
        print("   - 'Who sends me the most emails?'")
        print("   - 'Show me emails from last week'")
        print("   - 'What are my most common email labels?'")
        print("   - 'How many unread emails do I have?'")
        print("   - 'Who emailed me most in 2023?'")
        print("\n📝 Type 'exit' or 'quit' to end the conversation.")
        print("🔧 Type 'model' to switch AI models.")
        print()

        while True:
            try:
                # Get user input
                user_input = input("You: ").strip()

                # Check for exit commands
                if user_input.lower() in ["exit", "quit", "bye"]:
                    print("👋 Goodbye! Thanks for chatting about your Gmail data.")
                    break

                # Check for model switch command
                if user_input.lower() == "model":
                    print("🔧 Switching AI model...")
                    new_model_name = show_model_options()
                    try:
                        agent = EmailAnalysisAgent(db_path, model_name=new_model_name)
                        print("✅ Model switched successfully!")
                    except Exception as e:
                        print(f"❌ Failed to switch model: {e}")
                    continue

                if not user_input:
                    continue

                # Get agent response
                print("🤖 Agent: ", end="", flush=True)
                response = agent.chat(user_input)
                print(response)
                print()  # Empty line for readability

            except KeyboardInterrupt:
                print("\n👋 Goodbye! Thanks for chatting about your Gmail data.")
                break
            except EOFError:
                print("\n👋 Goodbye! Thanks for chatting about your Gmail data.")
                break

    except ChatError as e:
        print(f"❌ Chat initialization failed: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        logger.error(f"Unexpected error in chat: {e}")


def ask_single_question(
    question: str,
    model: str = "gemini",
) -> str:
    """
    Ask a single question to the agent without starting interactive chat.
    Uses data directory from settings.

    Args:
        question (str): The question to ask.
        model (str): Model key to use (gemini, openai, claude).

    Returns:
        str: The agent's response.
    """
    # Configure chat-specific logging for single questions too
    setup_chat_logging()

    data_dir = settings.get("DATA_DIR")
    if not data_dir:
        return "❌ DATA_DIR not configured in settings"

    db_path = f"{data_dir}/{DATABASE_FILE_NAME}"

    if not os.path.exists(db_path):
        return f"❌ Database not found at {db_path}. Please sync your Gmail data first."

    try:
        model_name = get_model_name(model)
        agent = EmailAnalysisAgent(db_path, model_name=model_name)
        return agent.chat(question)
    except Exception as e:
        return f"❌ Error: {e}"
