from rich.progress import Progress, track
from collections import defaultdict
from itertools import chain

import pendulum
from imgmeta import console
from osxphotos import PhotosDB
from photoscript import PhotosLibrary
from sinaspider.model import Artist

from photosinfo.model import Photo


def update_table(db_photos):
    Photo.delete().where(Photo.uuid.not_in([p.uuid for p in db_photos])).execute()
    for p in track(db_photos, description='[blue]Updating table...', console=console):
        force_insert = False
        if not p.exiftool:
            console.log(f'no exif:=>{p.uuid}')
            continue
        elif not (photo := Photo.get_or_none(uuid=p.uuid)):
            force_insert = True
            meta = p.exiftool.asdict()
            row = {Photo.column_to_field(k): meta.get('XMP:%s' % k) for k in Photo._meta.columns}
            if d := row.get('date_created'):
                row['date_created'] = pendulum.parse(d, strict=False)
            photo = Photo(**row)
            photo.uuid = p.uuid
        photo.live_photo = p.live_photo
        photo.with_place = all(p.location)
        photo.favorite = p.favorite
        photo.save(force_insert=force_insert)


def _gen_album_info():
    alb2photos = defaultdict(set)
    for p in track(Photo.select(), description="[red]Generate album info...", console=console):
        artist = p.artist
        supplier = p.image_supplier_name
        supplier = supplier.lower() if supplier else supplier
        uid = p.image_supplier_id
        top_fold = [supplier or 'no_supplier']
        second_fold = []
        album = [artist or 'no_artist']
        if supplier == 'weibo':
            if not uid:
                second_fold = ['weibo']
            else:
                artist = Artist.from_id(uid)
                second_fold = [artist.album]
                album = [artist.realname or artist.username]
        fold = top_fold + second_fold
        alb2photos[tuple(fold + album)].add(p.uuid)
        if p.favorite:
            alb2photos[tuple(fold + ['favorite'])].add(p.uuid)
            alb2photos[('favorite',)].add(p.uuid)

    return sorted(alb2photos.items(), key=lambda x: len(x[1]) if 'favorite' not in x[0] else 99999)


def add_photo_to_album(photosdb: PhotosDB, photoslib: PhotosLibrary):
    Photo.delete().where(Photo.uuid.not_in([p.uuid for p in photosdb.photos()])).execute()
    albums = {}
    for a in photosdb.album_info:
        path = tuple(p.title for p in chain(a.folder_list, [a]))
        if 'favorite' in path:
            if unfav := [p.uuid for p in a.photos if not p.favorite]:
                unfav = photoslib.photos(uuid=unfav)
                photoslib.album(uuid=a.uuid).remove(unfav)
        albums[path] = a

    album_info = _gen_album_info()
    for alb_path, photo_uuids in track(album_info, console=console,
                                       description='Adding to album...',):
        if alb := albums.get(alb_path):
            photo_uuids -= {p.uuid for p in alb.photos}
            alb = photoslib.album(uuid=alb.uuid)
        else:
            *folder, album_name = alb_path
            if folder:
                alb = photoslib.make_album_folders(album_name, folder)
            else:
                alb = photoslib.create_album(album_name)

        if not photo_uuids:
            continue
        console.log(f'album {alb_path} => {len(photo_uuids)} photos')
        photos = list(photoslib.photos(uuid=photo_uuids))
        while photos:
            processing, photos = photos[:50], photos[50:]
            alb.add(processing)
