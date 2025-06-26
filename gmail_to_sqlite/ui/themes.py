"""Theme configuration for the Gmail-to-SQLite CLI using Rich."""

from rich.theme import Theme
from rich.style import Style

# Define the application theme following modern CLI design patterns
APP_THEME = Theme(
    {
        # Status and feedback colors
        "success": "bold green",
        "error": "bold red",
        "warning": "bold yellow",
        "info": "bold cyan",
        "muted": "dim white",
        # Agent and AI related
        "agent": "bold magenta",
        "ai_response": "white",
        "user_input": "bold blue",
        "model_name": "bold cyan",
        # Data and results
        "data_header": "bold white on blue",
        "data_row": "white",
        "data_highlight": "bold yellow",
        "query_sql": "bright_black",
        # UI elements
        "prompt": "bold green",
        "command": "bold blue",
        "option": "cyan",
        "brand": "bold magenta",
        # Progress and status
        "progress_bar": "blue",
        "progress_text": "white",
        "spinner": "cyan",
        # Tables and structured data
        "table_header": "bold blue",
        "table_border": "bright_black",
        "table_footer": "dim cyan",
    }
)


def get_theme() -> Theme:
    """Get the application theme."""
    return APP_THEME


# Pre-defined styles for common elements
STYLES = {
    "brand_header": Style(color="magenta", bold=True),
    "section_title": Style(color="blue", bold=True),
    "emphasis": Style(color="yellow", bold=True),
    "subtle": Style(color="bright_black"),
    "success_icon": Style(color="green", bold=True),
    "error_icon": Style(color="red", bold=True),
    "warning_icon": Style(color="yellow", bold=True),
    "info_icon": Style(color="cyan", bold=True),
}
