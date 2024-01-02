"""
photosinfo
"""
from rich.console import Console
from rich.progress import (
    BarColumn, Progress,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn
)
from rich.theme import Theme

__version__ = '0.2.0'
custom_theme = Theme({
    "info": "dim cyan",
    "warning": "bold bright_yellow on dark_orange",
    "error": "bold bright_red on dark_red",
    "notice": "bold magenta"
})
console = Console(theme=custom_theme, width=130)


def get_progress(disable=False):
    columns = [
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(
            "[progress.percentage]{task.completed} of "
            "{task.total:>2.0f}({task.percentage:>02.1f}%)"),
        TimeRemainingColumn()
    ]
    return Progress(*columns, console=console,
                    disable=disable)
