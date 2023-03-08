import math
from collections import OrderedDict, defaultdict
from itertools import chain

import pendulum
from osxphotos import PhotosDB, QueryOptions
from photoscript import PhotosLibrary
from playhouse.shortcuts import model_to_dict

from photosinfo import console, get_progress
from photosinfo.model import Photo


def _get_photo_to_alb():
    from insmeta.model import Artist as InsArtist
    from sinaspider.model import Artist as SinaArtist
    from twimeta.model import Artist as TwiArtist
    kls_dict = {
        'weibo': SinaArtist,
        'instagram': InsArtist,
        'twitter': TwiArtist
    }

    supplier_dict = defaultdict(lambda: defaultdict(list))
    username_in_weibo = {a.username: a for a in SinaArtist}
    username_in_insweibo = {
        a.username for a in InsArtist} & set(username_in_weibo)

    for p in Photo:
        supplier = p.image_supplier_name
        uid = p.image_supplier_id or p.image_creator_name
        supplier_dict[supplier][uid].append(p)

    photo2album = {}

    for supplier, uids_dict in supplier_dict.items():
        supplier = supplier.lower() if supplier else 'no_supplier'
        if supplier == 'weiboliked':
            for uid, photos in uids_dict.items():
                if (pic_num := len(photos)) > 20:
                    album = photos[0].artist
                else:
                    album = str(math.ceil(pic_num / 10) * 10)
                for p in photos:
                    photo2album[p] = (supplier, p.title.split('⭐️')[1], album)
        elif not (kls := kls_dict.get(supplier)):
            assert list(uids_dict) == [None]
            for p in uids_dict[None]:
                album = p.album or p.artist or 'no_artist'
                photo2album[p] = (supplier, None, album)
        else:
            for uid, photos in uids_dict.items():
                if uid is None:
                    for p in photos:
                        photo2album[p] = (supplier, supplier, p.artist)
                    continue
                artist = kls.from_id(uid)
                username = artist.username
                if username in username_in_weibo:
                    first_folder = 'weibo'
                    artist = username_in_weibo[username]
                else:
                    first_folder = supplier
                for p in photos:
                    if p.artist != username:
                        second_folder = 'problem'
                        album = 'problem'
                        photo2album[p] = (first_folder, second_folder, album)
                        continue
                    if not (folder := artist.folder):
                        folder = 'ins' if p.artist in username_in_insweibo else None
                    if folder:
                        second_folder = folder
                        if 0 < artist.photos_num < 50:
                            album = 'small'
                        else:
                            album = username
                    elif first_folder in ['instagram', 'twitter']:
                        second_folder = None
                        album = 'small' if artist.photos_num < 30 else username
                    else:
                        for flag in [500, 200, 100, 50]:
                            if artist.photos_num >= flag:
                                second_folder = str(flag)
                                album = username
                                break
                        else:
                            second_folder = 'small'
                            for flag in [20, 10, 5, 2, 1]:
                                if artist.photos_num >= flag:
                                    album = str(flag)
                                    break
                            else:
                                assert False

                    photo2album[p] = (first_folder, second_folder, album)
    return photo2album


def _gen_album_info(photo2album):
    alb2photos = defaultdict(set)
    for p, (supplier, second_folder, album) in photo2album.items():
        folder = (supplier, second_folder) if second_folder else (supplier,)
        alb2photos[folder + (album,)].add(p.uuid)
        if second_folder in ['recent', 'super', 'new']:
            alb2photos[folder + ('all',)].add(p.uuid)
        if p.favorite:
            alb2photos[folder + ('favorite',)].add(p.uuid)
            alb2photos[(supplier, 'favorite')].add(p.uuid)
            alb2photos[('favorite',)].add(p.uuid)
        if (p.image_supplier_name and supplier != 'weiboliked' and
                p.date > pendulum.now().subtract(months=3)):
            alb2photos[('refresh',)].add(p.uuid)
        alb2photos[(supplier, 'all')].add(p.uuid)
    return alb2photos


def _get_keywords_album(photosdb: PhotosDB, alb2photo):
    query = QueryOptions(keyword=photosdb.keywords)
    photos = photosdb.query(query)
    for p in photos:
        alb2photo[('keyword', p.keywords[0] or 'empty')].add(p.uuid)


def add_photo_to_album(photosdb: PhotosDB, photoslib: PhotosLibrary):
    albums = {}
    for a in photosdb.album_info:
        path = tuple(p.title for p in chain(a.folder_list, [a]))
        albums[path] = a

    photo2album = _get_photo_to_alb()
    album_info = _gen_album_info(photo2album)
    _get_keywords_album(photosdb, album_info)

    album_info = OrderedDict(sorted(album_info.items(), key=lambda x: len(
        x[1]) if 'favorite' not in x[0] else 9999999))

    with get_progress() as progress:
        for alb_path, photo_uuids in progress.track(
                album_info.items(), description='Adding to album...'):
            alb = albums.pop(alb_path, None)
            if alb is not None:
                album_uuids = {p.uuid for p in alb.photos if not p.intrash}
                protect = 'refresh' in alb.title and len(alb.photos) < 2000

                if not protect and (unexpected := (album_uuids - photo_uuids)):
                    unexpected_photo = Photo.get_by_id(unexpected.pop())
                    console.log(f'{alb_path}: exists unexpected photo... ')
                    console.log(model_to_dict(unexpected_photo))
                    console.log(f'the unexpectedphoto will added to album:=>'
                                f'{photo2album[unexpected_photo]}')
                    console.log(f'Recreating {alb_path}')
                    photoslib.delete_album(photoslib.album(uuid=alb.uuid))
                    alb = None

            if alb:
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

        for alb_path, alb in progress.track(
                albums.items(), description="Deleting album..."):
            if "Untitled Album" in alb_path:
                continue
            console.log(f'Deleting {alb_path}...')
            alb = photoslib.album(uuid=alb.uuid)
            photoslib.delete_album(alb)
