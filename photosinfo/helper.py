from osxphotos import QueryOptions
from photoscript import PhotosLibrary
from pypinyin import lazy_pinyin

from photosinfo import get_progress


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
