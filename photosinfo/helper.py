from osxphotos import QueryOptions
from photoscript import PhotosLibrary
from pypinyin import lazy_pinyin

from photosinfo import console, get_progress
from photosinfo.model import Photo


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


def update_table(photosdb, photoslib: PhotosLibrary, tag_uuid=False):
    photos = photosdb.photos(intrash=False)
    _deleted_count = Photo.delete().where(Photo.uuid.not_in(
        [p.uuid for p in photos])).execute()
    console.log(f'Delete {_deleted_count} photos')

    with get_progress() as progress:
        process_uuid = {p.uuid for p in photos}
        process_uuid -= {p.uuid for p in Photo.select()}
        process_photos = [p for p in photos if p.uuid in process_uuid]
        rows = []
        failed_uuid = []
        new_uuid = []
        for p in progress.track(
                process_photos, description='Updating table...'):
            try:
                rows.append(Photo.info_to_row(p))
                new_uuid.append(p.uuid)
            except AttributeError:
                failed_uuid.append(p.uuid)

        if tag_uuid:
            if query_new_uuid := [p.uuid for p in photosdb.query(
                    QueryOptions(keyword=['new_uuid']))]:
                for p in photoslib.photos(uuid=query_new_uuid):
                    p.keywords = p.keywords.copy().remove('new_uuid')
            if query_failed_uuid := [p.uuid for p in photosdb.query(
                    QueryOptions(keyword=['failed_uuid']))]:
                for p in photoslib.photos(uuid=query_failed_uuid):
                    p.keywords = p.keywords.copy().remove('failed_uuid')

            if new_uuid:
                for p in photoslib.photos(uuid=new_uuid):
                    p.keywords += ['new_uuid']
            if failed_uuid:
                for p in photoslib.photos(uuid=failed_uuid):
                    p.keywords += ['failed_uuid']

        Photo.insert_many(rows).execute()

    favor_uuid = {p.uuid for p in photos if p.favorite}
    favor_uuid -= {p.uuid for p in Photo.select().where(Photo.favorite)}
    unfavor_uuid = {p.uuid for p in photos if not p.favorite}
    unfavor_uuid -= {p.uuid for p in Photo.select().where(~Photo.favorite)}
    Photo.update(favorite=True).where(Photo.uuid.in_(favor_uuid)).execute()
    Photo.update(favorite=False).where(Photo.uuid.in_(unfavor_uuid)).execute()

    hiden_uuid = {p.uuid for p in photos if p.hidden}
    hiden_uuid -= {p.uuid for p in Photo.select().where(Photo.hidden)}
    unhidden_uuid = {p.uuid for p in photos if not p.hidden}
    unhidden_uuid -= {p.uuid for p in Photo.select().where(~Photo.hidden)}
    Photo.update(hidden=True).where(Photo.uuid.in_(hiden_uuid)).execute()
    Photo.update(hidden=False).where(Photo.uuid.in_(unhidden_uuid)).execute()


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
