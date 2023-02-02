"""
photosinfo
"""
from rich.console import Console
from rich.progress import Progress, BarColumn, TimeRemainingColumn
from rich.theme import Theme

__version__ = '0.2.0'
custom_theme = Theme({
    "info": "dim cyan",
    "warning": "magenta",
    "error": "bold red"
})
console = Console(theme=custom_theme)


def get_progress():
    return Progress("[progress.description]{task.description}", BarColumn(),
                    "[progress.percentage]{task.completed} of {task.total:>2.0f}({task.percentage:>02.1f}%)",
                    TimeRemainingColumn(), console=console)
