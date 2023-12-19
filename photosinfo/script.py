from collections import defaultdict
from pathlib import Path

import pendulum
import questionary
from exiftool import ExifToolHelper
from osxphotos import PhotosDB
from photoscript import PhotosLibrary
from rich.prompt import Confirm, Prompt
from typer import Option, Typer

from photosinfo import console
from photosinfo.helper import update_keywords, update_table
from photosinfo.model import Girl, Photo
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
def album(recreate: bool = Option(False, "--recreate", "-r"),
          tag_uuid: bool = Option(False, "--tag-uuid", "-t")):
    photosdb = PhotosDB()
    photoslib = PhotosLibrary()
    console.log('update table...')
    update_table(photosdb, photoslib, tag_uuid)
    Girl.update_table()
    console.log('add photo to album...')
    get_album = GetAlbum(photosdb, photoslib)
    get_album.create_album(recreating=recreate)
    console.log('updating keywords....')
    update_keywords(photosdb, photoslib, get_album.keywords_info)


@app.command()
def girl(prompt: bool = Option(False, "--prompt", "-p")):
    Girl.update_table(prompt)
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


@app.command()
def weibo_extra(img_dir: Path):

    with ExifToolHelper() as et:
        metas = et.get_metadata(img_dir)
        ids = {meta['XMP:ImageUniqueID'] for meta in metas}
    uuids = [p.uuid for p in Photo.select().where(
        Photo.image_unique_id.in_(ids))]
    photoslib = PhotosLibrary()
    photoslib.create_album('WeiboExtra').add(photoslib.photos(uuid=uuids))


@app.command()
def dup_new(img_dir: Path):
    photoslib = PhotosLibrary()

    usernames_new = {girl.username for girl in Girl.select().where(
        Girl.sina_new | Girl.inst_new | Girl.red_new)}

    with ExifToolHelper() as et:
        metas = et.get_metadata(img_dir, params='-r')
    usernames = {meta['XMP:Artist'] for meta in metas}
    if not usernames.issubset(usernames_new):
        raise ValueError(
            f'not all artists are new: {usernames - usernames_new}')
    photos = Photo.select().where(Photo.artist.in_(usernames))
    albums = defaultdict(list)
    for photo in photos:
        if photo.image_supplier_name == 'WeiboSavedFail':
            continue
        assert photo.image_supplier_name in ['Weibo', 'Instagram', 'RedBook']
        albums[photo.artist].append(photo.uuid)
    assert 'all' not in albums
    albums = sorted(albums.items(), reverse=True)
    if len(albums) > 1:
        albums.append(['all', {p.uuid for p in photos}])
    for album_name, photos in albums:
        console.log(f'create album (dup_new, {album_name})')
        alb = photoslib.make_album_folders(album_name, ['locked.dup_new'])
        console.log(
            f'add {len(photos)} photos to album (locked.dup_new, {album_name})')
        photos = list(photoslib.photos(uuid=photos))
        while photos:
            processing, photos = photos[:50], photos[50:]
            alb.add(processing)


@app.command()
def new_uuids(days: int = 1):
    console.log(f'searching new added photos in {days} day(s)')
    query = Photo.select().where(
        Photo.row_created > pendulum.now().subtract(days=days))
    if uuids := [p.uuid for p in query]:
        photoslib = PhotosLibrary()
        album_name = f'New_in_{days}_day'
        console.log(f'add {len(uuids)} photos to album {album_name}')
        photoslib.create_album(album_name).add(
            photoslib.photos(uuid=uuids))
    else:
        console.log('no new photos')


@app.command()
def artist():
    while username := Prompt.ask('请输入用户名:smile:'):
        if not (girl := Girl.get_or_none(username=username)):
            console.log(f'用户 {username} 不在列表中')
            continue
        console.log(girl)
        console.print(
            f"which folder ? current is [bold red]{girl.folder}[/bold red]")
        folder = questionary.select("choose folder:", choices=[
            'recent', 'super', 'no-folder', 'less']).unsafe_ask()
        if folder == 'no-folder':
            folder = None
        if girl.folder == folder:
            continue
        ques = f'change folder from {girl.folder} to {folder} ?'
        if questionary.confirm(ques).unsafe_ask():
            girl.folder = folder
            girl.save()
            console.print(f'{girl.username}: '
                          f'folder changed to [bold red]{folder}[/bold red]')


@app.command()
def search(search_for: str, num: int = 5):
    from photosinfo.model import GirlSearch
    GirlSearch.add_querys()
    if search_for not in ['sina', 'inst', 'red']:
        console.log('col must be sina, inst or red')
        return
    query = (GirlSearch.select()
             .where(GirlSearch.search_for == search_for)
             .where(~GirlSearch.searched)
             .order_by(GirlSearch.username.desc())
             )
    query_recent = query.where(GirlSearch.folder == 'recent')
    query_super = query.where(GirlSearch.folder == 'super')
    query = query_recent or query_super or query
    usernames = sorted({s.username for s in query[:num]})
    query = query.where(GirlSearch.username.in_(usernames))
    for s in query:
        s: GirlSearch
        console.log(s)
        console.log(s.search_url, style='bold red')
        console.log()

    if not questionary.confirm('searched?', default=False).unsafe_ask():
        return
    console.log('saving...')
    for s in query:
        s.searched = True
        s.save()
