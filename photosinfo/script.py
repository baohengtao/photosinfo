from pathlib import Path

import exiftool
import pendulum
from rich.progress import track
from typer import Typer

from photosinfo import console
from photosinfo.model import Photo
from photosinfo.photosinfo import update_table, PhotosDB, PhotosLibrary, add_photo_to_album

app = Typer()


@app.command()
def update(added_since: float = -1):
    photosdb = PhotosDB()
    Photo.delete().where(Photo.uuid.not_in(
        [p.uuid for p in photosdb.photos()])).execute()
    if added_since == -1:
        added_since = pendulum.from_timestamp(0)
    else:
        added_since = pendulum.now().subtract(days=added_since)
    console.log('update table...')
    fav_uuids = update_table(photosdb.photos(), added_since=added_since)
    update_artist()
    return photosdb, added_since, fav_uuids


@app.command()
def tidy_photo_in_album(added_since: float = -1):
    photosdb, added_since, fav_uuids = update(added_since)
    console.log('add photo to album...')
    photoslib = PhotosLibrary()
    add_photo_to_album(photosdb, photoslib,
                       imported_since=added_since, extra_uuids=fav_uuids)


@app.command()
def update_artist():
    from sinaspider.model import Artist as SinaArtist
    from insmeta.model import Artist as InsArtist
    from twimeta.model import Artist as TwiArtist
    for Artist in [SinaArtist, InsArtist, TwiArtist]:
        for artist in track(Artist.select(), description='Updating artist...'):
            if artist.folder == 'new' and artist.photos_num:
                artist = Artist.from_id(artist.user_id, update=True)
            username = artist.realname or artist.username
            select_all = Photo.select().where((Photo.image_supplier_id == artist.user_id)
                                              | (Photo.artist == username))
            select_favor = select_all.where(Photo.favorite == True)
            select_recent = select_all.where(
                Photo.date_added > pendulum.now().subtract(days=180))
            artist.photos_num = select_all.count()
            artist.recent_num = select_recent.count()
            artist.favor_num = select_favor.count()
            artist.save()


