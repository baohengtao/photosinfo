import pendulum
from rich.progress import track
from typer import Typer

from photosinfo import console
from photosinfo.model import Photo
from photosinfo.photosinfo import (
    PhotosDB, PhotosLibrary,
    add_photo_to_album, update_table)
from collections import Counter, defaultdict
app = Typer()


@app.command()
def tidy_photo_in_album(added_since: float = -1,
                        refresh_favor: bool = False,
                        new_artist: bool = False):
    if added_since == -1:
        added_since = pendulum.from_timestamp(0)
    else:
        added_since = pendulum.now().subtract(days=added_since)
    photosdb = PhotosDB()
    console.log('update table...')
    update_table(photosdb)
    update_artist(new_artist)
    console.log('add photo to album...')
    photoslib = PhotosLibrary()
    add_photo_to_album(photosdb, photoslib,
                       imported_since=added_since,
                       refresh_favor=refresh_favor)


@app.command()
def update_artist(new_artist: bool = False):
    from sinaspider.model import Artist as SinaArtist
    from insmeta.model import Artist as InsArtist
    from twimeta.model import Artist as TwiArtist
    from playhouse.shortcuts import update_model_from_dict
    kls_dict = {
        'Weibo': SinaArtist,
        'Instagram': InsArtist,
        'Twitter': TwiArtist
    }
    # collections of uids
    uids_info = defaultdict(set)
    # counter of username
    username_info = defaultdict(
        lambda: Counter(photos_num=0, recent_num=0, favor_num=0))
    for p in Photo:
        supplier = p.image_supplier_name
        uid = p.image_supplier_id or p.image_creator_name
        if supplier and uid:
            assert isinstance(uid, int) == (supplier != 'Twitter')
            assert p.artist
            update = {'photos_num'}
            if p.date_added > pendulum.now().subtract(days=180):
                update.add('recent_num')
            if p.favorite:
                update.add('favor_num')
            username_info[p.artist].update(update)
            uids_info[supplier].add(uid)

    for supplier, kls in kls_dict.items():
        uids = uids_info[supplier].copy()
        rows = list(kls)
        for row in rows:
            if row.user_id not in uids:
                assert row.username not in username_info
            else:
                uids.remove(row.user_id)
        rows.extend(kls.from_id(uid) for uid in uids)
        for row in rows:
            update_model_from_dict(row, username_info[row.username])
            row.save()
        if new_artist:
            ids = {row.user_id for row in rows if row.folder == 'new'}
            ids &= uids_info[supplier]
            for id_ in ids:
                kls.from_id(id_, update=True)
