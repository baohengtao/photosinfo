
import math
from collections import OrderedDict, defaultdict
from itertools import chain

import pendulum
from insmeta.model import Artist as InsArtist
from osxphotos import PhotosDB, QueryOptions
from photoscript import PhotosLibrary
from playhouse.shortcuts import model_to_dict
from sinaspider.model import Artist as SinaArtist
from twimeta.model import Artist as TwiArtist

from photosinfo import console, get_progress
from photosinfo.model import Photo

kls_dict = {
    'weibo': SinaArtist,
    'instagram': InsArtist,
    'twitter': TwiArtist
}


class GetAlbum:
    def __init__(self,
                 photosdb: PhotosDB = None,
                 photoslib: PhotosLibrary = None) -> None:
        self.photosdb = photosdb
        self.photoslib = photoslib
        for kls in kls_dict.values():
            for k in kls:
                k.from_id(k.user_id)
        self.username_in_weibo = {a.username: a for a in SinaArtist}
        self.username_in_insweibo = {
            a.username for a in InsArtist} & set(self.username_in_weibo)
        self.supplier_dict = self.get_supplier_dict()
        self.photo2album = {}
        for supplier, uids_dict in self.supplier_dict.items():
            for uid, photos in uids_dict.items():
                self.get_photo2album(supplier, uid, photos)
        self.album_info = self.get_album_info()

    @staticmethod
    def get_supplier_dict():
        supplier_dict = defaultdict(lambda: defaultdict(list))
        for p in Photo:
            supplier = p.image_supplier_name
            uid = p.image_supplier_id or p.image_creator_name
            supplier_dict[supplier][uid].append(p)
        return supplier_dict

    def get_photo2album(self, supplier, uid, photos):
        supplier = supplier.lower() if supplier else 'no_supplier'
        if supplier == 'weiboliked':
            if (pic_num := len(photos)) > 20:
                album = photos[0].artist
            else:
                album = str(math.ceil(pic_num/10)*10)
            for p in photos:
                self.photo2album[p] = (supplier, p.title.split('⭐️')[1], album)
        elif supplier not in kls_dict:
            assert uid is None
            for p in photos:
                album = p.album or p.artist or 'no_artist'
                self.photo2album[p] = (supplier, None, album)
        elif uid is None:
            for p in photos:
                self.photo2album[p] = (supplier, supplier, p.artist)
        else:
            artist = kls_dict[supplier].from_id(uid)
            if (username := artist.username) in self.username_in_weibo:
                first_folder = 'weibo'
                artist = self.username_in_weibo[username]
            else:
                first_folder = supplier
            if username in self.username_in_insweibo:
                second_folder = 'ins'
            else:
                second_folder = artist.folder
            if second_folder:
                album = 'small' if artist.photos_num < 50 else username
            elif first_folder in ['instagram', 'twitter']:
                album = 'small' if artist.photos_num < 30 else username
            else:
                for flag in [200, 100, 50]:
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
            for p in photos:
                if p.artist != username:
                    self.photo2album[p] = (first_folder, None, 'problem')
                else:
                    self.photo2album[p] = (first_folder, second_folder, album)

    def get_album_info(self):
        album_info = defaultdict(set)
        for p, (supplier, second_folder, album) in self.photo2album.items():
            folder = (supplier, second_folder) if second_folder else (supplier,)
            album_info[folder + (album,)].add(p.uuid)
            if second_folder in ['recent', 'super', 'new']:
                album_info[folder + ('all',)].add(p.uuid)
            if p.favorite:
                album_info[folder + ('favorite',)].add(p.uuid)
                album_info[(supplier, 'favorite')].add(p.uuid)
                album_info[('favorite',)].add(p.uuid)
            if (p.image_supplier_name and supplier != 'weiboliked' and
                    p.date > pendulum.now().subtract(months=3)):
                album_info[('refresh',)].add(p.uuid)
            album_info[(supplier, 'all')].add(p.uuid)
        if self.photosdb:
            query = QueryOptions(keyword=self.photosdb.keywords)
            for p in self.photosdb.query(query):
                album_info[('keyword', p.keywords[0] or 'empty')].add(p.uuid)
        album_info = OrderedDict(sorted(album_info.items(), key=lambda x: len(
            x[1]) if 'favorite' not in x[0] else 9999999))
        return album_info

    def create_album(self):
        albums = {}
        for a in self.photosdb.album_info:
            path = tuple(p.title for p in chain(a.folder_list, [a]))
            albums[path] = a

        with get_progress() as progress:
            for alb_path, photo_uuids in progress.track(
                    self.album_info.items(), description='Adding to album...'):
                alb = albums.pop(alb_path, None)
                if alb is not None:
                    album_uuids = {p.uuid for p in alb.photos if not p.intrash}
                    protect = 'refresh' in alb.title and len(alb.photos) < 2000
                    if not protect and (unexpected := (album_uuids - photo_uuids)):
                        unexpected_photo = Photo.get_by_id(unexpected.pop())
                        console.log(f'{alb_path}: exists unexpected photo... ')
                        console.log(model_to_dict(unexpected_photo))
                        console.log(f'the unexpectedphoto will added to album:=>'
                                    f'{self.photo2album[unexpected_photo]}')
                        console.log(f'Recreating {alb_path}')
                        self.photoslib.delete_album(
                            self.photoslib.album(uuid=alb.uuid))
                        alb = None

                if alb:
                    photo_uuids -= {p.uuid for p in alb.photos}
                    alb = self.photoslib.album(uuid=alb.uuid)
                else:
                    *folder, album_name = alb_path
                    if folder:
                        alb = self.photoslib.make_album_folders(
                            album_name, folder)
                    else:
                        alb = self.photoslib.create_album(album_name)
                if photo_uuids:
                    console.log(
                        f'album {alb_path} => {len(photo_uuids)} photos')
                else:
                    continue
                photos = list(self.photoslib.photos(uuid=photo_uuids))
                while photos:
                    processing, photos = photos[:50], photos[50:]
                    alb.add(processing)

            for alb_path, alb in progress.track(
                    albums.items(), description="Deleting album..."):
                if "Untitled Album" in alb_path:
                    continue
                console.log(f'Deleting {alb_path}...')
                alb = self.photoslib.album(uuid=alb.uuid)
                self.photoslib.delete_album(alb)
