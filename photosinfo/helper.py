from pathlib import Path

import pendulum
from osxphotos import QueryOptions
from photoscript import PhotosLibrary
from pypinyin import lazy_pinyin

from photosinfo import console, get_progress

if not (d := Path('/Volumes/Art')).exists():
    d = Path.home()/'Pictures'
default_path = d / 'Photosinfo'


def update_keywords(photosdb,
                    photoslib: PhotosLibrary,
                    keywords_info: dict[str, set]
                    ):
    for keyword, uuids in keywords_info.items():
        query = QueryOptions(keyword=[keyword])
        uuids_keyword = {p.uuid for p in photosdb.query(query)}
        assert uuids_keyword.issubset(uuids)
        uuids -= uuids_keyword
        if not uuids:
            continue
        with get_progress() as progress:
            for p in progress.track(
                    list(photoslib.photos(uuid=uuids)),
                    description=f"adding keywords {keyword}"):
                assert keyword not in p.keywords
                p.keywords += [keyword]


def pinyinfy(username: str) -> str:
    if len(username) not in [2, 3, 4]:
        return
    pinyinfied = lazy_pinyin(username)
    if len(username) != len(pinyinfied):
        return
    idx = len(username) // 2
    first_name = "".join(pinyinfied[:idx]).capitalize()
    last_name = "".join(pinyinfied[idx:]).capitalize()
    return " " .join([first_name, last_name])


def logsaver_decorator(func):
    from functools import wraps
    from inspect import signature

    """Decorator to save console log to html file"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            with console.capture():
                console.print_exception(show_locals=True)
            raise
        finally:
            callargs = signature(func).bind(*args, **kwargs).arguments
            download_dir: Path = callargs.get('download_dir', default_path)
            save_log(func.__name__, download_dir)
    return wrapper


def save_log(func_name, download_dir):
    from rich.terminal_theme import MONOKAI
    download_dir.mkdir(parents=True, exist_ok=True)
    time_format = pendulum.now().format('YY-MM-DD_HHmmss')
    log_file = f"{func_name}_{time_format}.html"
    console.log(f'Saving log to {download_dir / log_file}')
    console.save_html(download_dir / log_file, theme=MONOKAI)
