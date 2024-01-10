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
from photosinfo.helper import update_keywords
from photosinfo.model import Girl, GirlSearch, Photo
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
    Photo.update_table(photosdb, photoslib, tag_uuid=tag_uuid)
    Girl.update_table()


@app.command()
def album(recreate: bool = Option(False, "--recreate", "-r"),
          tag_uuid: bool = Option(False, "--tag-uuid", "-t")):
    photosdb = PhotosDB()
    photoslib = PhotosLibrary()
    console.log('update table...')
    Photo.update_table(photosdb, photoslib, tag_uuid)
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
        if not (new_name := Prompt.ask(
                'Input the username you want to change to').strip()):
            continue
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
        if photo.image_supplier_name in ['WeiboSavedFail', 'WeiboLiked']:
            continue
        assert photo.image_supplier_name in [
            'Weibo', 'Instagram', 'RedBook', 'Aweme']
        album_name = photo.artist + ('_edited' if photo.edited else '')
        albums[album_name].append(photo.uuid)
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
def search_user(update: bool = False):
    if update:
        GirlSearch.add_querys()
    usernames = {g.username for g in GirlSearch.select().where(
        ~GirlSearch.searched)}
    while username := Prompt.ask('Input username you want search :smile:'):
        if usernames_partial := {
                g.username for g in GirlSearch.select()
                .where(GirlSearch.username ** f'%{username}%')}:
            if len(usernames_partial) == 1:
                username = usernames_partial.pop()
            else:
                username = questionary.select(
                    'which one?', choices=usernames_partial).unsafe_ask()
        elif usernames:
            console.log(f'user {username} not found', style='error')
            username = usernames.pop()
            console.log(f'using {username} instead')
        girl = Girl.get_by_id(username)

        girl.print()
        searches = GirlSearch.select().where(GirlSearch.username == username)
        for i, s in enumerate(searches, start=1):
            s: GirlSearch
            console.log(f'searching index {i}', style='bold red')
            console.log(s)
            console.log(s.search_url, style='bold green on dark_green')
            console.log()

        while id := Prompt.ask('Do you find any result? '
                               'input id to mark searched'):
            s = searches[int(id)-1]
            console.log(s)
            if result := Prompt.ask(f'input url of {s.username}'):
                s.search_result = result.split('?')[0].strip().strip('/')
                s.searched = True
                console.log(s)
                if Confirm.ask('save?', default=True):
                    s.save()
                    for s in GirlSearch.select().where(
                            GirlSearch.username == s.username,
                            GirlSearch.search_for == s.search_for,
                            GirlSearch.search_result.is_null()):
                        console.log('\ndeleting...')
                        console.log(s)
                        s.delete_instance()
                    break
        else:
            if not questionary.confirm('searched?', default=False).unsafe_ask():
                continue
            for s in searches:
                s.searched = True
                s.save()
                console.log('\nsaving...', style='notice')
                console.log(s)


@app.command()
def search(update: bool = False):
    if update:
        GirlSearch.add_querys()
    query = (GirlSearch.select()
             #  .where(GirlSearch.search_for == search_for)
             .where(~GirlSearch.searched)
             .order_by(GirlSearch.username.desc())
             )
    if not (search_fors := {s.search_for for s in query}):
        console.log('all user have been searched')
        return
    search_for = questionary.select(
        'which one?', choices=search_fors).unsafe_ask()
    query = query.where(GirlSearch.search_for == search_for)
    query_recent = query.where(GirlSearch.folder == 'recent')
    query_super = query.where(GirlSearch.folder == 'super')
    if not (query := query_recent or query_super or query):
        console.log('all user have been searched')
        return
    query_dict = defaultdict(list)
    for s in query:
        query_dict[s.username].append(s)

    while query_dict:
        username, searches = query_dict.popitem()
        console.rule(f'searching {username}...({len(query_dict)+1} left)')
        Girl.get_by_id(username).print()
        for i, s in enumerate(searches, start=1):
            s: GirlSearch
            console.log(f'searching index {i}', style='bold red')
            console.log(s)
            console.log(s.search_url, style='bold red')
            console.log()

        while idx := Prompt.ask('Do you find any result? '
                                'input the index to mark searched'):
            s = searches[int(idx)-1]
            console.log(s)
            if result := Prompt.ask(f'input url of {s.username}'):
                s.search_result = result.split('?')[0].strip().strip('/')
                s.searched = True
                console.log(s)
                if Confirm.ask('save?', default=True):
                    s.save()
                    for s in GirlSearch.select().where(
                            GirlSearch.username == s.username,
                            GirlSearch.search_for == s.search_for,
                            GirlSearch.search_result.is_null()):
                        console.log('\ndeleting...')
                        console.log(s)
                        s.delete_instance()
                    break
        else:
            if not questionary.confirm('searched?', default=False).unsafe_ask():
                continue
            for s in searches:
                s.searched = True
                s.save()
                console.log('\nsaving...', style='notice')
                console.log(s)
        print('\n'*3)
    search(update=False)
