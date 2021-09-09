import os
from collections import defaultdict
from itertools import chain

import osxphotos.albuminfo
import photoscript
from loguru import logger
from osxphotos import photosdb
from sinaspider import Artist as Artist_Weibo


class PhotosInfo:
    from photosinfo.database import photos_table as table

    def __init__(self):
        photoslib_path = os.path.expanduser('~/Pictures/照片图库.photoslibrary')
        self.photosdb = photosdb.PhotosDB(photoslib_path)
        self.photoslib = photoscript.PhotosLibrary()

    def update_table(self):
        uuid_list = []
        for p in self.photosdb.photos():
            uuid_list.append(p.uuid)
            row = self.table.find_one(uuid=p.uuid)
            if not row:
                meta = p.exiftool.asdict()
                row = {k: meta.get('XMP:%s' % k) for k in self.table.columns}
                row['uuid'] = p.uuid
                logger.info(f'insert {p.uuid}')
                self.table.insert(row)
            row.update(live_photo=p.live_photo,
                       with_place=p.with_place,
                       favorite=p.favorite)
            self.table.upsert(row, ['uuid'])

        for p in self.table:
            if p['uuid'] not in uuid_list:
                self.table.delete(uuid=p['uuid'])
                logger.info(f'delete {p["uuid"]}')

    def _gen_album_info(self):
        """
        return a dict:
            key: path of album (tuple)
            value: set of photos uuid (set)
        """
        alb2photos = defaultdict(set)
        for p in self.table:
            artist = p['Artist']
            supplier = p['ImageSupplierName']
            uid = p['ImageSuplierID']

            if uid and supplier.lower() == 'weibo':
                artist_info = Artist_Weibo(int(uid))
                album = artist_info['album'].split('/') + [artist_info['artist']]
            else:
                album = (supplier or 'no_supplier', artist or 'no_artist')
            alb2photos[tuple(album)].add(p.uuid)
        return alb2photos

    def add_photo_to_album(self):
        albums = dict()
        for a in self.photosdb.album_info:
            path = tuple(p.title for p in chain(a.folder_list, [a, ]))
            albums[path] = a

        for alb_path, uuids in self._gen_album_info().items():
            if not uuids:
                continue
            if alb := albums.get(alb_path):
                photos_in_album = set(p.uuid for p in alb.photos)
                uuids = uuids - photos_in_album
                alb = self.photoslib.album(uuid=alb.uuid)
            else:
                *folder, album_name = alb_path
                if folder:
                    alb = self.photoslib.make_album_folders(album_name, folder)
                else:
                    alb = self.photoslib.create_album(album_name)
            photos = self.photoslib.photos(uuid=uuids)
            photos = list(photos)
            print(
                f'Adding {len(photos)} photos to album {"/".join(alb_path)}')
            while photos:
                processing, photos = photos[:50], photos[50:]
                alb.add(processing)


class AlbumClean:
    def __init__(self):
        self.photos_lib = photoscript.PhotosLibrary()
        self.photos_db = photosdb.PhotosDB()

    def rm_empty_folder(self, folder: osxphotos.albuminfo.FolderInfo):
        albs, subfolders = [], []
        for album_ in folder.album_info:
            if not self.rm_empty_album(album_):
                albs.append(album_)
        for subf in folder.subfolders:
            if not self.rm_empty_folder(subf):
                subfolders.append(subf)
        if albs or subfolders:
            return False
        if not folder.parent:
            print(folder.uuid, folder.title)
            print('deleting', folder.title)
            self.photos_lib.delete_folder(
                self.photos_lib.folder(uuid=folder.uuid))
        return True

    def rm_empty_album(self, album: osxphotos.albuminfo.AlbumInfo):
        if not album.photos:
            print(album.uuid, album.title)
            print('deleting album', album.title)
            self.photos_lib.delete_album(
                self.photos_lib.album(uuid=album.uuid))
            return True
        else:
            return False

    def clean_empty_album(self):
        for album in self.photos_db.album_info:
            self.rm_empty_album(album)
        for folder in self.photos_db.folder_info:
            self.rm_empty_folder(folder)
