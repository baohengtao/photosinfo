import math
from collections import Counter, OrderedDict, defaultdict
from itertools import chain

import pendulum
from osxphotos import PhotosDB
from photoscript import PhotosLibrary
from playhouse.shortcuts import model_to_dict

from photosinfo import console, get_progress
from photosinfo.model import Photo


def update_table(photosdb):
    photos = photosdb.photos()
    Photo.delete().where(Photo.uuid.not_in(
        [p.uuid for p in photos])).execute()

    with get_progress() as progress:
        process_uuid = {p.uuid for p in photos}
        process_uuid -= {p.uuid for p in Photo.select()}
        process_photos = [p for p in photos if p.uuid in process_uuid]
        rows = []
        for p in progress.track(
                process_photos, description='Updating table...'):
            rows.append(Photo.info_to_row(p))
        Photo.insert_many(rows).execute()

    favor_uuid = {p.uuid for p in photos if p.favorite}
    favor_uuid -= {p.uuid for p in Photo.select().where(Photo.favorite)}
    unfavor_uuid = {p.uuid for p in photos if not p.favorite}
    unfavor_uuid -= {p.uuid for p in Photo.select().where(~Photo.favorite)}
    Photo.update(favorite=True).where(Photo.uuid.in_(favor_uuid)).execute()
    Photo.update(favorite=False).where(Photo.uuid.in_(unfavor_uuid)).execute()


def update_artist(new_artist: bool = False):
    from insmeta.model import Artist as InsArtist
    from playhouse.shortcuts import update_model_from_dict
    from sinaspider.model import Artist as SinaArtist
    from twimeta.model import Artist as TwiArtist
    kls_dict = {
        'Weibo': SinaArtist,
        'Instagram': InsArtist,
        'Twitter': TwiArtist
    }
    # collections of uids
    uids_info = defaultdict(set)
    # counter of username
    username_info = defaultdict(
        lambda: Counter(photos_num=0, recent_num=0, favor_num=0))
    for p in Photo:
        supplier = p.image_supplier_name
        uid = p.image_supplier_id or p.image_creator_name
        if supplier and uid:
            assert isinstance(uid, int) == (supplier != 'Twitter')
            assert p.artist
            update = {'photos_num'}
            if p.date_added > pendulum.now().subtract(days=180):
                update.add('recent_num')
            if p.favorite:
                update.add('favor_num')
            username_info[p.artist].update(update)
            uids_info[supplier].add(uid)

    for supplier, kls in kls_dict.items():
        uids = uids_info[supplier].copy()
        rows = list(kls)
        for row in rows:
            if row.user_id not in uids:
                name = row.realname or row.username
                assert name not in username_info, (name, row.user_id)
            else:
                uids.remove(row.user_id)
        rows.extend(kls.from_id(uid) for uid in uids)
        for row in rows:
            stast = username_info[row.realname or row.username]
            update_model_from_dict(row, stast)
            row.save()
        if new_artist:
            ids = {row.user_id for row in rows if row.folder == 'new'}
            ids &= uids_info[supplier]
            for id_ in ids:
                artist = kls.from_id(id_, update=True)
                artist.folder = 'recent'
                artist.save()


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
    username_in_weibo = {(a.realname or a.username): a for a in SinaArtist}
    username_in_insweibo = {(a.realname or a.username)
                            for a in InsArtist} & set(username_in_weibo)

    for p in Photo:
        supplier = p.image_supplier_name
        uid = p.image_supplier_id or p.image_creator_name
        supplier_dict[supplier][uid].append(p)

    photo2album = {}

    for supplier, uids_dict in supplier_dict.items():
        supplier = supplier.lower() if supplier else 'no_supplier'
        if supplier == 'weiboliked':
            for uid, photos in uids_dict.items():
                if (pic_num := len(photos)) > 50:
                    album = photos[0].artist
                else:
                    album = str(math.ceil(pic_num / 10) * 10)
                for p in photos:
                    photo2album[p] = (supplier, None, album)
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
                        continue
                    if not (folder := artist.folder):
                        folder = 'ins' if p.artist in username_in_insweibo else None
                    if folder:
                        second_folder = folder
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
        if (p.image_supplier_name and
                p.date > pendulum.now().subtract(months=3)):
            alb2photos[('refresh',)].add(p.uuid)
        alb2photos[('all', supplier)].add(p.uuid)
    alb2photos = OrderedDict(sorted(alb2photos.items(), key=lambda x: len(
        x[1]) if 'favorite' not in x[0] else 9999999))
    return alb2photos


def add_photo_to_album(photosdb: PhotosDB, photoslib: PhotosLibrary):
    albums = {}
    for a in photosdb.album_info:
        path = tuple(p.title for p in chain(a.folder_list, [a]))
        albums[path] = a

    photo2album = _get_photo_to_alb()
    album_info = _gen_album_info(photo2album)

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
