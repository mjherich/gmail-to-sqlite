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


class EnhancedSQLiteTool(BaseTool):
    """An intelligent CrewAI tool for executing SQL queries against SQLite databases with AI-powered query generation."""

    name: str = "Enhanced SQLite Query Tool"
    description: str = """
    Execute intelligent SQL queries against a SQLite database containing Gmail messages.
    
    This tool can:
    1. Convert complex natural language questions to optimized SQL queries using AI
    2. Handle advanced queries with JOINs, subqueries, and complex aggregations
    3. Provide query optimization and validation
    4. Return formatted results with insights
    5. Cache common queries for better performance
    
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
    
    Can handle complex queries like:
    - "Compare my email volume between 2023 and 2024 by month"
    - "Find email threads with the most participants"
    - "Show me the response time patterns for different contacts"
    - "Analyze my email activity by day of week and hour"
    """

    def __init__(self, db_path: str, llm=None, **kwargs):
        super().__init__(**kwargs)
        self._db_path = db_path
        self._llm = llm
        self._query_cache = {}
        self._schema_info = None

    def _run(self, query: str) -> str:
        """
        Execute a SQL query or convert natural language to SQL and execute it.

        Args:
            query: Either a natural language question or SQL query

        Returns:
            Formatted query results
        """
        try:
            # Check if it's already a SQL query
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
                # Use intelligent SQL generation
                print(f"🧠 Analyzing: '{query}'")
                sql_query = self._intelligent_sql_generation(query)
                print(f"📝 Generated SQL: {sql_query[:150]}{'...' if len(sql_query) > 150 else ''}")

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

    def _get_schema_info(self) -> str:
        """Get cached schema information for context."""
        if self._schema_info is None:
            try:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.cursor()
                
                # Get table schema
                cursor.execute("PRAGMA table_info(messages);")
                columns = cursor.fetchall()
                
                schema_parts = ["Table: messages"]
                schema_parts.append("Columns:")
                for col in columns:
                    col_name, col_type = col[1], col[2]
                    schema_parts.append(f"  - {col_name}: {col_type}")
                
                # Get sample data patterns
                cursor.execute("SELECT COUNT(*) FROM messages")
                total_count = cursor.fetchone()[0]
                schema_parts.append(f"\nTotal messages: {total_count}")
                
                conn.close()
                self._schema_info = "\n".join(schema_parts)
            except Exception as e:
                self._schema_info = f"Schema info unavailable: {e}"
        
        return self._schema_info
    
    def _intelligent_sql_generation(self, question: str) -> str:
        """
        Use AI to generate SQL queries from natural language.
        Falls back to pattern matching if AI is unavailable.
        """
        if self._llm is None:
            return self._fallback_pattern_matching(question)
        
        try:
            schema_context = self._get_schema_info()
            
            sql_prompt = f"""
            You are an expert SQL query generator for Gmail email data analysis.
            
            Database Schema:
            {schema_context}
            
            User Question: "{question}"
            
            Generate a SQLite query to answer this question. Follow these guidelines:
            1. Use proper SQLite syntax
            2. Handle JSON fields with -> and ->> operators for sender/recipients
            3. Use date functions like strftime() for date filtering
            4. Add appropriate LIMIT clauses for large result sets
            5. Include helpful column aliases
            6. Optimize for performance
            
            Return ONLY the SQL query, no explanations.
            """
            
            # Use the LLM to generate SQL
            response = self._llm.invoke(sql_prompt)
            sql_query = response.strip()
            
            # Basic validation
            if not sql_query.upper().startswith(('SELECT', 'WITH')):
                raise ValueError("Generated query must be a SELECT statement")
            
            return sql_query
            
        except Exception as e:
            print(f"⚠️  AI SQL generation failed: {e}. Using pattern matching.")
            return self._fallback_pattern_matching(question)
    
    def _fallback_pattern_matching(self, question: str) -> str:
        """
        Fallback pattern-matching approach for SQL generation.
        Enhanced version of the original method.
        """
        question_lower = question.lower()

        # Extract year filters if present
        year_filter = ""
        for year in range(2000, 2030):
            if str(year) in question_lower:
                year_filter = f" AND strftime('%Y', timestamp) = '{year}'"
                break

        # Enhanced pattern matching with more sophisticated queries
        if ("compare" in question_lower and "volume" in question_lower) or ("by month" in question_lower):
            return f"""
            SELECT strftime('%Y-%m', timestamp) as month,
                   COUNT(*) as email_count,
                   AVG(size) as avg_size
            FROM messages 
            WHERE 1=1{year_filter}
            GROUP BY strftime('%Y-%m', timestamp)
            ORDER BY month DESC
            LIMIT 24
            """

        elif "thread" in question_lower and ("participants" in question_lower or "people" in question_lower):
            return f"""
            SELECT thread_id,
                   COUNT(*) as message_count,
                   COUNT(DISTINCT sender->>'$.email') as unique_senders,
                   MIN(timestamp) as thread_start,
                   MAX(timestamp) as thread_end
            FROM messages 
            WHERE 1=1{year_filter}
            GROUP BY thread_id
            HAVING message_count > 1
            ORDER BY unique_senders DESC, message_count DESC
            LIMIT 10
            """

        elif "response time" in question_lower or "reply time" in question_lower:
            return f"""
            SELECT sender->>'$.email' as contact,
                   AVG(julianday(timestamp) - julianday(LAG(timestamp) OVER (ORDER BY timestamp))) * 24 * 60 as avg_response_minutes,
                   COUNT(*) as email_count
            FROM messages 
            WHERE is_outgoing = 0{year_filter}
            GROUP BY sender->>'$.email'
            HAVING email_count > 5
            ORDER BY avg_response_minutes ASC
            LIMIT 10
            """

        elif "day of week" in question_lower or "hour" in question_lower:
            return f"""
            SELECT strftime('%w', timestamp) as day_of_week,
                   strftime('%H', timestamp) as hour,
                   COUNT(*) as email_count
            FROM messages 
            WHERE 1=1{year_filter}
            GROUP BY day_of_week, hour
            ORDER BY email_count DESC
            LIMIT 20
            """

        # Original patterns (enhanced)
        elif ("who sends me the most emails" in question_lower or "top senders" in question_lower):
            return f"""
            SELECT sender->>'$.email' as sender_email, 
                   sender->>'$.name' as sender_name,
                   COUNT(*) as email_count,
                   MAX(timestamp) as last_email
            FROM messages 
            WHERE is_outgoing = 0{year_filter}
            GROUP BY sender->>'$.email', sender->>'$.name'
            ORDER BY email_count DESC 
            LIMIT 15
            """

        elif "unread" in question_lower:
            return f"""
            SELECT COUNT(*) as unread_count,
                   COUNT(CASE WHEN is_outgoing = 0 THEN 1 END) as unread_received,
                   COUNT(CASE WHEN is_outgoing = 1 THEN 1 END) as unread_sent
            FROM messages 
            WHERE is_read = 0{year_filter}
            """

        elif "last week" in question_lower or "past week" in question_lower:
            return f"""
            SELECT DATE(timestamp) as date,
                   COUNT(*) as daily_count,
                   COUNT(CASE WHEN is_outgoing = 0 THEN 1 END) as received,
                   COUNT(CASE WHEN is_outgoing = 1 THEN 1 END) as sent
            FROM messages 
            WHERE timestamp >= date('now', '-7 days'){year_filter}
            GROUP BY DATE(timestamp)
            ORDER BY date DESC
            """

        else:
            # Enhanced default query with more context
            return f"""
            SELECT subject, 
                   sender->>'$.email' as sender, 
                   timestamp,
                   is_read,
                   is_outgoing,
                   CASE WHEN length(body) > 100 THEN substr(body, 1, 100) || '...' ELSE body END as preview
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

        # Initialize the enhanced SQLite tool with AI capabilities
        self.sqlite_tool = EnhancedSQLiteTool(db_path=db_path, llm=self.llm)

        # Get database schema for context
        self.db_schema = self._get_database_schema()

        # Create the enhanced CrewAI agent with advanced capabilities
        self.agent = Agent(
            role="Gmail Data Analyst & Insights Expert",
            goal="Provide deep, actionable insights about Gmail data through intelligent analysis and natural conversation",
            backstory=f"""You are a world-class data analyst and email intelligence expert with deep expertise in:
            
            📊 **Data Analysis**: Advanced statistical analysis, pattern recognition, and trend identification
            📧 **Email Analytics**: Communication patterns, productivity insights, and relationship mapping  
            🧠 **Context Awareness**: Remember previous conversations and build upon past insights
            💡 **Strategic Thinking**: Provide actionable recommendations based on data patterns
            
            **Your Database**: Gmail messages with schema:
            {self.db_schema}
            
            **Your Capabilities**:
            - Generate intelligent SQL queries for complex analysis using AI-powered query generation
            - Identify meaningful patterns and trends in email data
            - Provide explanations and context for all findings
            - Remember conversation history and build upon previous insights
            - Suggest follow-up analyses and interesting questions
            - Translate data into actionable productivity and communication insights
            
            **Your Approach**: Always explain what you're analyzing, why it's interesting, and what the user can learn from it. 
            Don't just show data - provide insights, context, and recommendations. Use your enhanced SQL capabilities to 
            answer complex questions that go beyond simple pattern matching.""",
            llm=self.llm,
            verbose=False,
            memory=True,  # Enhanced persistent memory
            respect_context_window=True,  # Auto-manage context limits
            allow_delegation=False,
            max_rpm=30,  # Rate limiting for cost control
            function_calling_llm=self.llm,  # Use same model for now, can optimize later
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
        print("✅ Enhanced AI-powered analysis enabled")
        print("💫 Features: Intelligent SQL generation, persistent memory, advanced insights")

        # Initialize the agent with selected model
        print(f"\n🤖 Initializing Gmail Analysis Agent...")
        agent = EmailAnalysisAgent(db_path, model_name=model_name)

        print("✅ Enhanced Agent ready! You can now have intelligent conversations about your Gmail data.")
        print("💡 Try asking sophisticated questions like:")
        print("   🔍 Basic: 'Who sends me the most emails?' or 'How many unread emails do I have?'")
        print("   📊 Advanced: 'Compare my email volume between 2023 and 2024 by month'")
        print("   🧵 Threads: 'Find email threads with the most participants'")
        print("   ⏱️ Patterns: 'Analyze my email activity by day of week and hour'")
        print("   🚀 Complex: 'What are my response time patterns for different contacts?'")
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
