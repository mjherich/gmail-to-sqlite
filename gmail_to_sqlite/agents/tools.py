"""Enhanced tools for Gmail data analysis with better UI integration."""

import sqlite3
from typing import Optional, Dict, Any, Callable

from crewai.tools import BaseTool

from ..ui import ChatDisplay


class EnhancedSQLiteTool(BaseTool):
    """Intelligent CrewAI tool for executing SQL queries with beautiful display output."""

    name: str = "Enhanced SQLite Query Tool"
    description: str = """
    Execute SQL queries against a SQLite database containing email messages.
    
    This tool converts natural language questions to SQL queries using AI and executes them.
    It handles queries about senders, dates, message content, and database analysis.
    
    The database contains a 'messages' table with columns for message metadata,
    sender/recipient information, timestamps, and content.
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
            return self._simple_fallback_query()

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
                    f"AI SQL generation failed: {e}. Using simple fallback.",
                    "Fallback",
                )
            return self._simple_fallback_query()

    def _simple_fallback_query(self) -> str:
        """Simple fallback query when AI generation fails."""
        return """
        SELECT subject, sender, timestamp, is_read, is_outgoing
        FROM messages
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
