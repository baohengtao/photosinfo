from collections import defaultdict
from itertools import chain

import pendulum
from osxphotos import PhotosDB
from photoscript import PhotosLibrary

from photosinfo import get_progress, console
from photosinfo.model import Photo
from collections import OrderedDict


def update_table(photosdb, added_since=pendulum.from_timestamp(0)):
    Photo.delete().where(Photo.uuid.not_in(
        [p.uuid for p in photosdb])).execute()
    recent_uuid = {p.uuid for p in photosdb if p.date_added > added_since}

    with get_progress() as progress:
        process_uuid = recent_uuid - {p.uuid for p in Photo.select()}
        process_photos = [p for p in photosdb if p.uuid in process_uuid]
        for p in progress.track(
                process_photos, description='Updating table...'):
            Photo.add_to_db(p)

    favor_uuid = {p.uuid for p in photosdb if p.favorite}
    favor_uuid -= {p.uuid for p in Photo.select().where(
        Photo.favorite == True)}
    unfavor_uuid = {p.uuid for p in photosdb if not p.favorite}
    unfavor_uuid -= {p.uuid for p in Photo.select().where(
        Photo.favorite == False)}
    Photo.update(favorite=True).where(Photo.uuid.in_(favor_uuid)).execute()
    Photo.update(favorite=False).where(Photo.uuid.not_in(favor_uuid)).execute()
    favor_uuid = {p.uuid for p in photosdb if p.favorite}
    return favor_uuid


def _gen_twitter_info(uid, p_artist):
    from twimeta.model import Artist, User
    try:
        artist = Artist.from_id(uid)
        assert artist
    except (User.DoesNotExist, AssertionError):
        return 'uid_doesnot_exist', p_artist
    username = artist.realname or artist.username
    album = username if p_artist == username else 'problem_album'
    if artist.folder:
        second_folder = artist.folder
    else:
        for flag in [500, 200, 100, 50]:
            if artist.photos_num > flag:
                second_folder = str(flag)
                break
        else:
            second_folder = 'small'
            album = 'small'
    return second_folder, album


def _gen_insta_info(supplier, uid, p_artist):
    assert supplier == 'instagram'
    from insmeta.model import Artist as InsArtist
    from sinaspider.model import Artist as WeiboArtist
    second_folder, album = None, p_artist
    if artist := InsArtist.from_id(id=int(uid)):
        username = artist.realname or artist.username
        if artist_wb := WeiboArtist.get_or_none(WeiboArtist.username == username):
            supplier = 'weibo'
            uid = artist_wb.user_id
            second_folder, album = _gen_weibo_info(uid, p_artist)
        else:
            album = username if p_artist == username else 'problem_album'
            for flag in [500, 200, 100, 50]:
                if artist.photos_num > flag:
                    second_folder = str(flag)
                    break
            else:
                second_folder = 'small'
                album = 'small'

    return supplier, second_folder, album


def _gen_weibo_info(uid, p_artist):
    from sinaspider.model import Artist
    if not uid:
        second_folder, album = 'weibo', p_artist
    else:
        artist = Artist.from_id(uid)
        username = artist.realname or artist.username
        if p_artist != username:
            second_folder = 'problem'
            album = 'problem'
        # elif artist.folder:
            # second_folder = artist.folder
            # album = username
        else:
            for flag in [500, 200, 100, 50]:
                if artist.photos_num > flag:
                    second_folder = artist.folder or str(flag)
                    album = username
                    break
            else:
                second_folder = artist.folder or 'small'
                album = 'small'
    return second_folder, album


def _gen_single_album_info(supplier, artist, uid, p_album):
    supplier = (supplier or 'no_supplier').lower()
    artist = artist or 'no_artist'
    try:
        uid = int(uid) if uid else None
    except ValueError:
        if supplier in ['instagram', 'weibo']:
            return supplier, None, 'uid_not_int'

    if supplier == 'instagram' and uid:
        supplier, second_folder, album = _gen_insta_info(supplier, uid, artist)
    elif supplier == 'weibo':
        second_folder, album = _gen_weibo_info(uid, artist)
    elif supplier == 'twitter':
        second_folder, album = _gen_twitter_info(uid, artist)
    else:
        second_folder = None
        album = artist
    if p_album:
        album = p_album
    return supplier, second_folder, album


def _get_album_in_db(photosdb: PhotosDB):
    """
    Generate a map of album_path to album_info object
    """
    albums = {}
    for a in photosdb.album_info:
        path = tuple(p.title for p in chain(a.folder_list, [a]))

        albums[path] = a
    return albums


def _gen_album_info(photosdb,
                    added_since: pendulum.DateTime = pendulum.from_timestamp(
                        0), extra_uuids=None):
    photos = Photo.select().where((Photo.date_added > added_since)
                                  | (Photo.uuid.in_(extra_uuids or {})))
    photos_refresh = {p.uuid for p in photosdb.photos()
                      if p.date > pendulum.now().subtract(days=30)}
    alb2photos = defaultdict(set)
    with get_progress() as progress:
        for p in progress.track(
                photos, description='Generating album info...'):
            supplier, second_folder, album = _gen_single_album_info(
                p.image_supplier_name, p.artist,
                p.image_supplier_id or p.image_creator_name,
                p.album)
            folder = (supplier, second_folder) if second_folder else (
                supplier,)
            alb2photos[folder + (album,)].add(p.uuid)
            if p.favorite:
                alb2photos[folder + ('favorite',)].add(p.uuid)
                alb2photos[(supplier, 'favorite')].add(p.uuid)
                alb2photos[('favorite',)].add(p.uuid)
            if p.image_supplier_name and p.uuid in photos_refresh:
                alb2photos[('refresh',)].add(p.uuid)
            if p.image_supplier_name:
                alb2photos[('all', p.image_supplier_name)].add(p.uuid)

    alb2photos = OrderedDict(sorted(alb2photos.items(), key=lambda x: len(
        x[1]) if 'favorite' not in x[0] else 99999))

    return alb2photos


def add_photo_to_album(photosdb: PhotosDB, photoslib: PhotosLibrary,
                       imported_since=pendulum.from_timestamp(0),
                       extra_uuids=None):

    for a in photosdb.album_info:
        if 'favor' in a.title:
            photoslib.delete_album(photoslib.album(uuid=a.uuid))

    Photo.delete().where(Photo.uuid.not_in(
        [p.uuid for p in photosdb.photos()])).execute()
    albums = _get_album_in_db(photosdb)
    album_info = _gen_album_info(photosdb, imported_since, extra_uuids)
    with get_progress() as progress:
        for alb_path, photo_uuids in progress.track(
                album_info.items(), description='Adding to album...'):
            if alb := albums.pop(alb_path, None):
                photo_uuids -= {p.uuid for p in alb.photos}
                alb = photoslib.album(uuid=alb.uuid)
            else:
                *folder, album_name = alb_path
                if folder:
                    alb = photoslib.make_album_folders(album_name, folder)
                else:
                    alb = photoslib.create_album(album_name)
            if photo_uuids:
                console.log(f'album {alb_path} => {len(photo_uuids)} photos')
            photos = list(photoslib.photos(uuid=photo_uuids)
                          ) if photo_uuids else []
            while photos:
                processing, photos = photos[:50], photos[50:]
                alb.add(processing)

        if imported_since == pendulum.from_timestamp(0):
            for alb_path, alb in progress.track(
                    albums.items(), description="Deleting album..."):
                if "Untitled" in alb_path:
                    continue
                console.log(f'Deleting {alb_path}...')
                alb = photoslib.album(uuid=alb.uuid)
                photoslib.delete_album(alb)
