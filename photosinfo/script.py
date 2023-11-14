from osxphotos import PhotosDB
from photoscript import PhotosLibrary
from typer import Option, Typer

from photosinfo import console
from photosinfo.helper import update_artist, update_keywords, update_table
from photosinfo.photosinfo import GetAlbum

app = Typer(
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=False
)


@app.command()
def refresh_table(tag_uuid: bool = Option(False, "--tag-uuid", "-t")):
    photosdb = PhotosDB()
    photoslib = PhotosLibrary()
    console.log('update table...')
    update_table(photosdb, photoslib, tag_uuid=tag_uuid)


@app.command()
def refresh_album(new_artist: bool = Option(False, "--new-artist", "-n"),
                  recreate: bool = Option(False, "--recreate", "-r"),
                  tag_uuid: bool = Option(False, "--tag-uuid", "-t")):
    photosdb = PhotosDB()
    photoslib = PhotosLibrary()
    console.log('update table...')
    update_table(photosdb, photoslib, tag_uuid)
    update_artist(new_artist)
    console.log('add photo to album...')
    get_album = GetAlbum(photosdb, photoslib)
    get_album.create_album(recreating=recreate)
    console.log('updating keywords....')
    update_keywords(photosdb, photoslib, get_album.keywords_info)
