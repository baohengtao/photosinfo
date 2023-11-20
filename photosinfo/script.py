from osxphotos import PhotosDB
from photoscript import PhotosLibrary
from rich.prompt import Confirm, Prompt
from typer import Option, Typer

from photosinfo import console
from photosinfo.helper import update_artist, update_keywords, update_table
from photosinfo.model import Girl
from photosinfo.photosinfo import GetAlbum

app = Typer(
    # pretty_exceptions_enable=True,
    # pretty_exceptions_show_locals=False
)


@app.command()
def table(tag_uuid: bool = Option(False, "--tag-uuid", "-t")):
    photosdb = PhotosDB()
    photoslib = PhotosLibrary()
    console.log('update table...')
    update_table(photosdb, photoslib, tag_uuid=tag_uuid)


@app.command()
def album(new_artist: bool = Option(False, "--new-artist", "-n"),
          recreate: bool = Option(False, "--recreate", "-r"),
          tag_uuid: bool = Option(False, "--tag-uuid", "-t")):
    photosdb = PhotosDB()
    photoslib = PhotosLibrary()
    console.log('update table...')
    update_table(photosdb, photoslib, tag_uuid)
    update_artist(new_artist)
    Girl.update_table()
    console.log('add photo to album...')
    get_album = GetAlbum(photosdb, photoslib)
    get_album.create_album(recreating=recreate)
    console.log('updating keywords....')
    update_keywords(photosdb, photoslib, get_album.keywords_info)


@app.command()
def girl():
    Girl.update_table()
    while username := Prompt.ask('请输入用户名:smile:').strip():
        if not (girl := Girl.get_or_none(username=username)):
            console.log(f'用户{username}不存在', style='error')
            continue
        console.log(girl)
        new_name = Prompt.ask(
            'Input the username you want to change to').strip()
        if Confirm.ask(f'change {username} to {new_name}', default=True):
            girl = girl.change_username(new_name)
            console.log(girl)
