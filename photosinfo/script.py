from osxphotos import PhotosDB
from photoscript import PhotosLibrary
from typer import Typer

from photosinfo import console
from photosinfo.helper import update_artist, update_table
from photosinfo.photosinfo import GetAlbum

app = Typer(
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=False
)


@app.command()
def tidy_photo_in_album(new_artist: bool = False):
    photosdb = PhotosDB()
    console.log('update table...')
    update_table(photosdb)
    update_artist(new_artist)
    console.log('add photo to album...')
    photoslib = PhotosLibrary()
    GetAlbum(photosdb, photoslib).create_album()
