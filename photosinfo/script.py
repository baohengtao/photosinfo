from osxphotos import PhotosDB
from photoscript import PhotosLibrary
from typer import Option, Typer

from photosinfo import console
from photosinfo.helper import update_artist, update_table
from photosinfo.photosinfo import GetAlbum

app = Typer(
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=False
)


@app.command()
def refresh_table():
    photosdb = PhotosDB()
    console.log('update table...')
    update_table(photosdb)


@app.command()
def refresh_album(new_artist: bool = Option(False, "--new-artist", "-n"),
                  recreate: bool = Option(False, "--recreate", "-r")):
    photosdb = PhotosDB()
    console.log('update table...')
    update_table(photosdb)
    update_artist(new_artist)
    console.log('add photo to album...')
    photoslib = PhotosLibrary()
    GetAlbum(photosdb, photoslib).create_album(recreating=recreate)
