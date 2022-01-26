from rich.console import Console
from rich.progress import Progress
from rich.theme import Theme
from rich import traceback
import typer, photoscript, osxphotos
__version__ = '0.2.0'
traceback.install(suppress=[typer, photoscript, osxphotos], show_locals=False)
custom_theme = Theme({
    "info": "dim cyan",
    "warning": "magenta",
    "error": "bold red"
})
console = Console(theme=custom_theme)
progress = Progress(console=console)
