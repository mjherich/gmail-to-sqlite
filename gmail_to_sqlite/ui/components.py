"""Reusable UI components for the Gmail-to-SQLite CLI."""

import time
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    MofNCompleteColumn,
    TimeElapsedColumn,
)
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.spinner import Spinner
from rich.align import Align

from .themes import get_theme, STYLES


class ProgressIndicator:
    """Modern progress indicators and spinners."""

    def __init__(self, console: Console):
        self.console = console

    @contextmanager
    def spinner(self, message: str):
        """Show a spinner with message."""
        with self.console.status(f"[spinner]{message}[/]", spinner="dots"):
            yield

    @contextmanager
    def progress_bar(self, total: int, description: str = "Processing"):
        """Show a progress bar."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            task = progress.add_task(description, total=total)
            yield progress, task


class StatusDisplay:
    """Status and notification displays."""

    def __init__(self, console: Console):
        self.console = console

    def success(self, message: str, title: Optional[str] = None):
        """Display a success message."""
        if title:
            self.console.print(f"[success]✅ {title}[/]: {message}")
        else:
            self.console.print(f"[success]✅ {message}[/]")

    def error(self, message: str, title: Optional[str] = None):
        """Display an error message."""
        if title:
            self.console.print(f"[error]❌ {title}[/]: {message}")
        else:
            self.console.print(f"[error]❌ {message}[/]")

    def warning(self, message: str, title: Optional[str] = None):
        """Display a warning message."""
        if title:
            self.console.print(f"[warning]⚠️  {title}[/]: {message}")
        else:
            self.console.print(f"[warning]⚠️  {message}[/]")

    def info(self, message: str, title: Optional[str] = None):
        """Display an info message."""
        if title:
            self.console.print(f"[info]ℹ️  {title}[/]: {message}")
        else:
            self.console.print(f"[info]ℹ️  {message}[/]")

    def panel(self, content: str, title: str, style: str = "info"):
        """Display content in a panel."""
        panel = Panel(content, title=title, border_style=style, padding=(1, 2))
        self.console.print(panel)


class TableBuilder:
    """Builder for creating beautiful tables."""

    def __init__(self, console: Console):
        self.console = console
        self.table = None

    def create(
        self, title: Optional[str] = None, caption: Optional[str] = None
    ) -> "TableBuilder":
        """Create a new table."""
        self.table = Table(
            title=title,
            caption=caption,
            show_header=True,
            header_style="table_header",
            border_style="table_border",
            caption_style="table_footer",
        )
        return self

    def add_column(
        self,
        name: str,
        justify: str = "left",
        style: Optional[str] = None,
        no_wrap: bool = False,
    ) -> "TableBuilder":
        """Add a column to the table."""
        if self.table:
            self.table.add_column(name, justify=justify, style=style, no_wrap=no_wrap)
        return self

    def add_row(self, *values: str) -> "TableBuilder":
        """Add a row to the table."""
        if self.table:
            self.table.add_row(*values)
        return self

    def show(self):
        """Display the table."""
        if self.table:
            self.console.print(self.table)


class ModelSelector:
    """Interactive model selection component."""

    def __init__(self, console: Console):
        self.console = console

    def show_models(self, models: Dict[str, Dict[str, str]]) -> str:
        """Display model options and get user selection."""
        # Create a beautiful model selection table
        table = Table(
            title="🤖 Available AI Models",
            show_header=True,
            header_style="table_header",
            border_style="table_border",
        )

        table.add_column("Option", style="option", justify="center", width=8)
        table.add_column("Model", style="model_name", no_wrap=True)
        table.add_column("Description", style="muted")
        table.add_column("Features", style="info")

        # Add model rows
        for key, model_info in models.items():
            features = model_info.get("features", "")
            table.add_row(
                f"[option]{key}[/]",
                f"[model_name]{model_info['name']}[/]",
                model_info["description"],
                f"[info]{features}[/]",
            )

        self.console.print(table)
        self.console.print()

        while True:
            choice = self.console.input(
                "[prompt]Select model (1-3) or press Enter for default: [/]"
            ).strip()

            if not choice:  # Default
                return models["1"]["key"]

            if choice in models:
                selected = models[choice]
                self.console.print(f"[success]✅ Selected: {selected['name']}[/]")
                return selected["key"]

            self.console.print("[error]❌ Invalid choice. Please select 1, 2, or 3.[/]")


class WelcomeScreen:
    """Welcome screen and feature showcase."""

    def __init__(self, console: Console):
        self.console = console

    def show(self, model_description: str):
        """Display the welcome screen."""
        # Brand header
        brand_text = Text("Gmail-to-SQLite", style=STYLES["brand_header"])
        brand_text.append(" AI Chat", style="bold white")

        # Feature highlights
        features_panel = Panel(
            """[info]🧠 Intelligent SQL Generation[/] - Convert natural language to optimized queries
[info]💾 Persistent Memory[/] - Remembers your conversation history
[info]📊 Advanced Analytics[/] - Pattern analysis beyond basic SQL
[info]🔍 Smart Insights[/] - AI-powered data interpretation
[info]⚡ Multi-Model Support[/] - Gemini, OpenAI, and Claude""",
            title="✨ Enhanced Features",
            border_style="cyan",
            padding=(1, 2),
        )

        # Usage examples
        examples_panel = Panel(
            """[muted]Basic:[/] 'Who sends me the most emails?' or 'How many unread emails?'
[muted]Advanced:[/] 'Compare my email volume between 2023 and 2024 by month'
[muted]Threads:[/] 'Find email threads with the most participants'
[muted]Patterns:[/] 'Analyze my email activity by day of week and hour'
[muted]Complex:[/] 'What are my response time patterns for different contacts?'""",
            title="💡 Try These Questions",
            border_style="yellow",
            padding=(1, 2),
        )

        # Commands help
        commands_panel = Panel(
            """[command]'exit'[/] or [command]'quit'[/] - End the conversation
[command]'model'[/] - Switch AI models""",
            title="🔧 Commands",
            border_style="blue",
            padding=(1, 2),
        )

        self.console.print()
        self.console.print(Align.center(brand_text))
        self.console.print()

        self.console.print(f"[model_name]🤖 Using {model_description}[/]")
        self.console.print()

        self.console.print(features_panel)
        self.console.print(examples_panel)
        self.console.print(commands_panel)
        self.console.print()
