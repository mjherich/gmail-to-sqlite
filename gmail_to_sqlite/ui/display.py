"""Main display manager for the Gmail-to-SQLite chat interface."""

import sys
from typing import Optional, Dict, Any
from contextlib import contextmanager

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.live import Live
from rich.spinner import Spinner

from .themes import get_theme
from .components import (
    ProgressIndicator, 
    StatusDisplay, 
    TableBuilder, 
    ModelSelector, 
    WelcomeScreen
)


class ChatDisplay:
    """Main display manager for the chat interface using Rich."""
    
    def __init__(self, width: Optional[int] = None):
        """Initialize the chat display with Rich console."""
        self.console = Console(
            theme=get_theme(),
            width=width,
            force_terminal=True,
            highlight=False  # Disable auto-highlighting to control our own styling
        )
        
        # Initialize component managers
        self.progress = ProgressIndicator(self.console)
        self.status = StatusDisplay(self.console)
        self.table = TableBuilder(self.console)
        self.model_selector = ModelSelector(self.console)
        self.welcome = WelcomeScreen(self.console)
        
        # Track current state
        self._current_session = None
        
    def show_welcome(self, model_description: str):
        """Display the welcome screen."""
        self.welcome.show(model_description)
        
    def show_model_selection(self, models: Dict[str, Dict[str, str]]) -> str:
        """Show model selection and return chosen model."""
        return self.model_selector.show_models(models)
        
    def show_initialization(self, model_description: str, session_id: Optional[str] = None):
        """Show initialization progress."""
        with self.progress.spinner("Initializing Gmail Analysis Agent"):
            # This would contain the actual initialization
            pass
            
        self.status.success("Enhanced Agent ready!", "Initialization Complete")
        if session_id:
            self.status.info(f"Using session: {session_id}", "Session")
        
    def show_processing(self, message: str = "Processing your question"):
        """Show processing indicator."""
        return self.progress.spinner(message)
        
    def show_query_execution(self, query: str, is_ai_generated: bool = False):
        """Display SQL query execution with syntax highlighting."""
        if is_ai_generated:
            self.status.info("AI generated query", "SQL Generation")
        
        # Show syntax highlighted SQL
        sql_syntax = Syntax(
            query, 
            "sql", 
            theme="monokai",
            line_numbers=False,
            background_color="default"
        )
        
        panel = Panel(
            sql_syntax,
            title="🔍 Executing Query",
            border_style="query_sql",
            padding=(0, 1)
        )
        self.console.print(panel)
        
    def show_query_results(self, results: str, row_count: Optional[int] = None):
        """Display query results in a formatted way."""
        if row_count:
            title = f"📊 Query Results ({row_count} rows)"
        else:
            title = "📊 Query Results"
            
        # Try to parse and format as table if it looks like tabular data
        if "|" in results and "-" in results:
            # This looks like a table format
            panel = Panel(
                f"[data_row]{results}[/]",
                title=title,
                border_style="info",
                padding=(1, 2)
            )
        else:
            # Regular text results
            panel = Panel(
                results,
                title=title,
                border_style="info",
                padding=(1, 2)
            )
            
        self.console.print(panel)
        
    def show_user_input(self, prompt: str = "You") -> str:
        """Get user input with styled prompt."""
        return self.console.input(f"[user_input]{prompt}:[/] ")
        
    def show_agent_response(self, response: str, agent_name: str = "🤖 Agent"):
        """Display agent response with proper formatting."""
        # Check if response contains markdown-like formatting
        if any(marker in response for marker in ['**', '*', '`', '#', '-', '1.']):
            # Render as markdown for better formatting
            try:
                markdown = Markdown(response)
                panel = Panel(
                    markdown,
                    title=f"[agent]{agent_name}[/]",
                    border_style="agent",
                    padding=(1, 2)
                )
            except:
                # Fallback to plain text if markdown parsing fails
                panel = Panel(
                    f"[ai_response]{response}[/]",
                    title=f"[agent]{agent_name}[/]",
                    border_style="agent", 
                    padding=(1, 2)
                )
        else:
            # Plain text response
            panel = Panel(
                f"[ai_response]{response}[/]",
                title=f"[agent]{agent_name}[/]",
                border_style="agent",
                padding=(1, 2)
            )
            
        self.console.print(panel)
        
    def show_error(self, error: str, title: str = "Error"):
        """Display error message."""
        self.status.error(error, title)
        
    def show_warning(self, warning: str, title: str = "Warning"):
        """Display warning message."""
        self.status.warning(warning, title)
        
    def show_info(self, info: str, title: str = "Info"):
        """Display info message."""
        self.status.info(info, title)
        
    def show_success(self, success: str, title: str = "Success"):
        """Display success message."""
        self.status.success(success, title)
        
    def show_goodbye(self):
        """Display goodbye message."""
        goodbye_text = Text("👋 Goodbye! Thanks for chatting about your Gmail data.", style="success")
        self.console.print()
        self.console.print(goodbye_text)
        
    def show_model_switch(self, new_model: str):
        """Show model switching process."""
        with self.progress.spinner("Switching AI model"):
            # This would contain the actual model switching
            pass
        self.status.success(f"Switched to {new_model}", "Model Switch")
        
    def print(self, text: str, style: Optional[str] = None):
        """Direct print method for custom content."""
        self.console.print(text, style=style)
        
    def print_panel(self, content: str, title: str, style: str = "info"):
        """Print content in a panel."""
        self.status.panel(content, title, style)
        
    def clear(self):
        """Clear the console."""
        self.console.clear()
        
    def rule(self, title: Optional[str] = None, style: str = "muted"):
        """Print a horizontal rule."""
        self.console.rule(title, style=style)
        
    @contextmanager
    def live_update(self, initial_content: str):
        """Context manager for live-updating content."""
        with Live(initial_content, console=self.console, auto_refresh=True) as live:
            yield live