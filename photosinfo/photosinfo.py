from collections import defaultdict
from itertools import chain

import pendulum
from osxphotos import PhotosDB
from photoscript import PhotosLibrary

from photosinfo import get_progress, console
from photosinfo.model import Photo
from collections import OrderedDict
from playhouse.shortcuts import model_to_dict


def update_table(photosdb):
    photos = photosdb.photos()
    Photo.delete().where(Photo.uuid.not_in(
        [p.uuid for p in photos])).execute()

    with get_progress() as progress:
        process_uuid = {p.uuid for p in photos}
        process_uuid -= {p.uuid for p in Photo.select()}
        process_photos = [p for p in photos if p.uuid in process_uuid]
        for p in progress.track(
                process_photos, description='Updating table...'):
            Photo.add_to_db(p)

    favor_uuid = {p.uuid for p in photos if p.favorite}
    favor_uuid -= {p.uuid for p in Photo.select().where(
        Photo.favorite == True)}
    unfavor_uuid = {p.uuid for p in photos if not p.favorite}
    unfavor_uuid -= {p.uuid for p in Photo.select().where(
        Photo.favorite == False)}
    Photo.update(favorite=True).where(Photo.uuid.in_(favor_uuid)).execute()
    Photo.update(favorite=False).where(Photo.uuid.in_(unfavor_uuid)).execute()


def _get_album_in_db(photosdb: PhotosDB):
    """
    Generate a map of album_path to album_info object
    """
    albums = {}
    for a in photosdb.album_info:
        path = tuple(p.title for p in chain(a.folder_list, [a]))

        albums[path] = a
    return albums


def _get_photo_to_alb():

    from sinaspider.model import Artist as SinaArtist
    from insmeta.model import Artist as InsArtist
    from twimeta.model import Artist as TwiArtist
    kls_dict = {
        'weibo': SinaArtist,
        'instagram': InsArtist,
        'twitter': TwiArtist
    }

    supplier_dict = defaultdict(lambda: defaultdict(set))
    username_in_weibo = {(a.realname or a. username): a for a in SinaArtist}

    for p in Photo:
        supplier = p.image_supplier_name
        uid = p.image_supplier_id or p.image_creator_name
        supplier_dict[supplier][uid].add(p)

    photo2album = {}

    for supplier, uids_dict in supplier_dict.items():
        supplier = supplier.lower() if supplier else 'no_supplier'
        if not (kls := kls_dict.get(supplier)):
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
                username = artist.realname or artist.username
                if username in username_in_weibo:
                    first_folder = 'weibo'
                    artist = username_in_weibo[username]
                else:
                    first_folder = supplier
                for p in photos:
                    if p.artist != username:
                        second_folder = 'problem'
                        album = 'problem'
                    elif artist.folder:
                        second_folder = artist.folder
                        if 0 < artist.photos_num < 50:
                            album = 'small'
                        else:
                            album = username
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

                    photo2album[p] = (first_folder, second_folder, album)
    return photo2album


def _gen_album_info3():
    photo2album = _get_photo_to_alb()
    alb2photos = defaultdict(set)
    for p, (supplier, second_folder, album) in photo2album.items():
        folder = (supplier, second_folder) if second_folder else (supplier,)
        alb2photos[folder + (album,)].add(p.uuid)
        if second_folder in ['recent', 'super']:
            alb2photos[folder + ('all',)].add(p.uuid)
        if p.favorite:
            alb2photos[folder + ('favorite',)].add(p.uuid)
            alb2photos[(supplier, 'favorite')].add(p.uuid)
            alb2photos[('favorite',)].add(p.uuid)
        if (p.image_supplier_name and
                p.date > pendulum.now().subtract(months=3)):
            alb2photos[('refresh',)].add(p.uuid)
        alb2photos[('all', supplier)].add(p.uuid)
    alb2photos = OrderedDict(sorted(alb2photos.items(), key=lambda x: len(
        x[1]) if 'favorite' not in x[0] else 9999999))
    return alb2photos


def add_photo_to_album(photosdb: PhotosDB, photoslib: PhotosLibrary):

    albums = _get_album_in_db(photosdb)
    # album_info = _gen_album_info(photosdb, imported_since)
    album_info = _gen_album_info3()

    with get_progress() as progress:
        for alb_path, photo_uuids in progress.track(
                album_info.items(), description='Adding to album...'):
            alb = albums.pop(alb_path, None)
            if alb is not None:
                album_uuids = {p.uuid for p in alb.photos if not p.intrash}
                if unexpected := (album_uuids - photo_uuids):
                    unexpected_photo = Photo.get_by_id(unexpected.pop())
                    console.log(f'{alb_path}: exists unexpected photo... ')
                    console.log(model_to_dict(unexpected_photo))
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
