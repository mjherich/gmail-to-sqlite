"""Enhanced tools for Gmail data analysis with better UI integration."""

import sqlite3
from typing import Optional, Dict, Any, Callable

from crewai.tools import BaseTool

from ..ui import ChatDisplay


class EnhancedSQLiteTool(BaseTool):
    """Intelligent CrewAI tool for executing SQL queries with beautiful display output."""

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

    def __init__(
        self,
        db_path: str,
        llm: Any = None,
        display_callback: Optional[Callable] = None,
        max_rows: Optional[int] = None,
        max_field_length: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._db_path = db_path
        self._llm = llm
        self._query_cache: Dict[str, str] = {}
        self._schema_info: Optional[str] = None
        self._display_callback = display_callback
        # Configurable limits - None means no limit
        self._max_rows = max_rows
        self._max_field_length = max_field_length

    def _run(self, query: str) -> str:
        """Execute a SQL query or convert natural language to SQL and execute it."""
        try:
            # Check if it's already a SQL query
            query_upper = query.strip().upper()
            is_sql = any(
                query_upper.startswith(cmd)
                for cmd in ["SELECT", "INSERT", "UPDATE", "DELETE", "WITH"]
            )

            if is_sql:
                sql_query = query
                if self._display_callback:
                    self._display_callback("show_query_execution", sql_query, False)
            else:
                # Use intelligent SQL generation
                if self._display_callback:
                    self._display_callback("show_processing", f"Analyzing: '{query}'")

                sql_query = self._intelligent_sql_generation(query)

                if self._display_callback:
                    self._display_callback("show_query_execution", sql_query, True)

            # Execute the query
            result = self._execute_sql_query(sql_query)

            # Show results through display callback if available
            if self._display_callback:
                lines = result.split("\n")
                row_count = (
                    len(lines) - 2 if len(lines) > 2 else 0
                )  # Subtract header and separator
                self._display_callback("show_query_results", result, row_count)

            return result

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            if self._display_callback:
                self._display_callback("show_error", error_msg, "SQL Error")
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
        """Use AI to generate SQL queries from natural language."""
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
            messages = [{"role": "user", "content": sql_prompt}]
            response = self._llm.call(messages)
            sql_query = response.strip()

            # Basic validation
            if not sql_query.upper().startswith(("SELECT", "WITH")):
                raise ValueError("Generated query must be a SELECT statement")

            return sql_query

        except Exception as e:
            if self._display_callback:
                self._display_callback(
                    "show_warning",
                    f"AI SQL generation failed: {e}. Using pattern matching.",
                    "Fallback",
                )
            return self._fallback_pattern_matching(question)

    def _fallback_pattern_matching(self, question: str) -> str:
        """Fallback pattern-matching approach for SQL generation."""
        question_lower = question.lower()

        # Extract year filters if present
        year_filter = ""
        for year in range(2000, 2030):
            if str(year) in question_lower:
                year_filter = f" AND strftime('%Y', timestamp) = '{year}'"
                break

        # Enhanced pattern matching with more sophisticated queries
        if ("compare" in question_lower and "volume" in question_lower) or (
            "by month" in question_lower
        ):
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

        elif "thread" in question_lower and (
            "participants" in question_lower or "people" in question_lower
        ):
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
        elif (
            "who sends me the most emails" in question_lower
            or "top senders" in question_lower
        ):
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

                # Apply configurable row limit
                rows_to_show = results
                if self._max_rows is not None:
                    rows_to_show = results[: self._max_rows]

                for row in rows_to_show:
                    formatted_row = []
                    for value in row:
                        if value is None:
                            formatted_row.append("NULL")
                        else:
                            str_value = str(value)
                            # Apply configurable field length limit
                            if (
                                self._max_field_length is not None
                                and len(str_value) > self._max_field_length
                            ):
                                str_value = (
                                    str_value[: self._max_field_length - 3] + "..."
                                )
                            formatted_row.append(str_value)
                    result_lines.append(" | ".join(formatted_row))

                # Show truncation message only if we actually truncated
                if self._max_rows is not None and len(results) > self._max_rows:
                    result_lines.append(
                        f"... ({len(results)} total rows, showing first {self._max_rows})"
                    )

                return "\n".join(result_lines)
            else:
                return f"Query executed successfully. {len(results)} rows affected."

        except Exception as e:
            return f"SQL Error: {e}"
