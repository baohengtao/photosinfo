from pathlib import Path

import exiftool
import pendulum
from rich.progress import track
from typer import Typer

from photosinfo import console
from photosinfo.model import Photo
from photosinfo.photosinfo import PhotosDB, PhotosLibrary, add_photo_to_album

app = Typer()


@app.command()
def update_table():
    from photosinfo.photosinfo import update_table
    photosdb = PhotosDB()
    console.log('update table...')
    update_table(photosdb)
    return photosdb


@app.command()
def tidy_photo_in_album(added_since: float = -1, 
                        refresh_favor: bool=False,
                        refresh_artist: bool=False):
    if added_since == -1:
        added_since = pendulum.from_timestamp(0)
    else:
        added_since = pendulum.now().subtract(days=added_since)
    photosdb = update_table()
    update_artist(refresh_artist)
    console.log('add photo to album...')
    photoslib = PhotosLibrary()
    add_photo_to_album(photosdb, photoslib,
                       imported_since=added_since,
                       refresh_favor=refresh_favor)


@app.command()
def update_artist(refresh_artist:bool=False):
    from sinaspider.model import Artist as SinaArtist
    from insmeta.model import Artist as InsArtist
    from twimeta.model import Artist as TwiArtist
    for Artist in [SinaArtist, InsArtist, TwiArtist]:
        for artist in track(Artist.select(), description='Updating artist...'):
            if refresh_artist and artist.folder == 'new' and artist.photos_num:
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


