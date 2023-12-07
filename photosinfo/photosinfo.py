import math
from collections import OrderedDict, defaultdict
from itertools import chain

import pendulum
from insmeta.model import Artist as InsArtist
from osxphotos import PhotosDB, QueryOptions
from photoscript import PhotosLibrary
from playhouse.shortcuts import model_to_dict
from redbook.model import Artist as RedArtist
from sinaspider.model import Artist as SinaArtist
from sinaspider.model import UserConfig
from twimeta.model import Artist as TwiArtist

from photosinfo import console, get_progress
from photosinfo.model import Girl, Photo

kls_dict = {
    'weibo': SinaArtist,
    'instagram': InsArtist,
    'redbook': RedArtist
}


class GetAlbum:
    def __init__(self,
                 photosdb: PhotosDB,
                 photoslib: PhotosLibrary = None) -> None:
        self.photosdb = photosdb
        self.photoslib = photoslib
        self.need_fix = set()
        for kls in kls_dict.values():
            for k in kls:
                k.from_id(k.user_id)
        self.supplier_dict = self.get_supplier_dict()
        self.photo2album: dict[Photo, tuple] = {}
        self.keywords_info: defaultdict[str, set] = defaultdict(set)
        for supplier, uids_dict in self.supplier_dict.items():
            for uid, photos in uids_dict.items():
                self.get_photo2album(supplier, uid, photos)
        assert len(self.photo2album) == len(
            Photo.select().where(~Photo.hidden))
        self.album_info = self.get_album_info()

    @staticmethod
    def get_supplier_dict():
        supplier_dict: defaultdict[str, defaultdict[str, list[Photo]]]
        supplier_dict = defaultdict(lambda: defaultdict(list))
        for p in Photo.select().where(~Photo.hidden):
            supplier = p.image_supplier_name
            uid = p.image_supplier_id or p.image_creator_name
            supplier_dict[supplier][uid].append(p)
        return supplier_dict

    def get_photo2album(self, supplier: str, uid: str, photos: list[Photo]):
        supplier = supplier.lower() if supplier else 'no_supplier'
        assert supplier != 'weibosaved'
        if supplier in ['weiboliked', 'weibosavedfail']:
            liked_by = photos[0].title.split('⭐️')[1]
            if (pic_num := len(photos)) > 50:
                album = photos[0].artist
            else:
                album = str(math.ceil(pic_num/10)*10)
            if uid in self.supplier_dict['Weibo']:
                folder = ('weibosaved', 'done', album)
            elif uc := UserConfig.get_or_none(user_id=uid):
                if uc.weibo_fetch_at:
                    assert uc.weibo_fetch is True
                    folder = ('weibosaved', 'fetched', album)
                else:
                    folder = ('weibosaved', 'added', album)
            elif photos[0].favorite:
                folder = ('weiboliked', "tbd", album)
            elif supplier == 'weiboliked':
                folder = ('weiboliked', None, '_'.join((liked_by, album)))
            else:
                folder = ('weiboliked', None, album)
            if supplier == 'weibosavedfail':
                folder = (supplier,) + folder[1:]
            for p in photos:
                self.photo2album[p] = folder
        elif supplier == 'twitter':
            artist = TwiArtist.from_id(uid)
            album = 'small' if len(photos) <= 32 else artist.username
            for p in photos:
                if p.artist != artist.username:
                    self.photo2album[p] = ('twitter', None, 'problem')
                    self.need_fix.add(p.uuid)
                else:
                    self.photo2album[p] = ('twitter', None, album)

        elif supplier not in kls_dict:
            assert uid is None
            for p in photos:
                album = p.album or p.artist or 'no_artist'
                self.photo2album[p] = (supplier, None, album)
        elif uid is None:
            for p in photos:
                self.photo2album[p] = (supplier, supplier, p.artist)
        else:
            username = kls_dict[supplier].from_id(uid).username
            girl: Girl = Girl.get_by_id(username)
            first_folder = supplier
            second_folder = girl.folder
            if girl.sina_id and girl.inst_id:
                first_folder = 'insweibo'
                second_folder = girl.folder or 'ins'
            elif girl.sina_id:
                first_folder = 'weibo'
            elif girl.inst_id:
                first_folder = 'instagram'

            SMALL_NUMBER = 32
            if second_folder:
                if (second_folder.startswith('recent')
                        or second_folder == 'new'):
                    SMALL_NUMBER = 0
                elif second_folder == 'super':
                    SMALL_NUMBER = 16
            elif first_folder == 'instagram':
                SMALL_NUMBER = 16

            album = 'small' if girl.total_num <= SMALL_NUMBER else username
            if first_folder == 'weibo' and not second_folder:
                second_folder = 'ord' if girl.total_num > 50 else 'small'
                for flag in [4, 8, 16, 32]:
                    if girl.total_num <= flag:
                        album = str(flag)
                        break
                else:
                    album = username
            if second_folder == 'super':
                second_folder = None

            if supplier != first_folder:
                self.keywords_info[supplier] |= {p.uuid for p in photos}

            for p in photos:
                if p.artist != username:
                    self.photo2album[p] = (first_folder, None, 'problem')
                    self.need_fix.add(p.uuid)
                else:
                    self.photo2album[p] = (first_folder, second_folder, album)

    def get_album_info(self) -> OrderedDict[tuple, set[str]]:
        album_info: dict[tuple, set[str]] = defaultdict(set)
        for p, (supplier, sec_folder, album) in self.photo2album.items():
            folder = (supplier, sec_folder) if sec_folder else (supplier,)
            album_info[folder + (album,)].add(p.uuid)
            if (sec_folder in ['super', 'new', 'ins', 'ins-super']
                    or 'recent' in (sec_folder or '')):
                album_info[folder + ('all',)].add(p.uuid)
            elif supplier == 'weibosaved':
                album_info[folder + ('all',)].add(p.uuid)
            if supplier != 'weiboliked':
                album_info[(supplier, 'all')].add(p.uuid)
                if sec_folder is None:
                    album_info[(supplier, 'root')].add(p.uuid)
            if p.favorite and supplier not in ['weiboliked', 'weibosaved']:
                album_info[folder + ('favorite',)].add(p.uuid)
                album_info[(supplier, 'favorite')].add(p.uuid)
                album_info[('favorite',)].add(p.uuid)
            if (p.image_supplier_name and
                supplier not in ['weiboliked', 'weibosaved'] and
                    p.date > pendulum.now().subtract(months=2)):
                album_info[('refresh',)].add(p.uuid)
        for alb_path in album_info.copy().keys():
            *folder,  album = alb_path
            for dup in ['root', 'all']:
                if album == dup:
                    break
                elif album_info[alb_path] == album_info[(*folder, dup)]:
                    album_info.pop((*folder, dup))

        if self.photosdb and (keywords := self.photosdb.keywords):
            query = QueryOptions(keyword=keywords)
            for p in self.photosdb.query(query):
                for keyword in p.keywords:
                    if 'location' in keyword.lower():
                        album_info[(keyword, )].add(p.uuid)
                    elif keyword not in kls_dict:
                        album_info[('keyword', keyword)].add(p.uuid)
                    else:
                        assert p.uuid in self.keywords_info[keyword]
        if self.need_fix:
            album_info[('need_fix', )] = self.need_fix.copy()
        album_info[('wide',)] = {
            p.uuid for p in self.photosdb.photos()
            if p.width > p.height and p.uuid in album_info[('favorite',)]}
        album_info = {k: v for k, v in album_info.items() if v}
        album_info = OrderedDict(sorted(album_info.items(), key=lambda x: len(
            x[1]) if 'favorite' not in x[0] else 9999999))
        album_info |= self.get_timeline_albums()
        album_info |= self.get_tag_new_albums()

        return album_info

    @staticmethod
    def get_tag_new_albums() -> OrderedDict[tuple, set[str]]:
        albums = {}
        collector = defaultdict(lambda: defaultdict(set))
        for p in Photo:
            collector[p.artist][p.image_supplier_name].add(p.uuid)

        for girl in Girl.select().where(
                Girl.sina_new | Girl.inst_new | Girl.red_new):
            if len(co := collector.get(girl.username, {})) <= 1:
                continue
            cmp = {'Weibo': girl.sina_new,
                   'Instagram': girl.inst_new, 'RedBook': girl.red_new}
            cmp = {k for k, v in cmp.items() if v}
            if not (cmp & set(co)):
                continue
            for supplier, uuids in co.items():
                album_name = f'{girl.username}_{supplier}'
                albums[('dup_new', album_name)] = uuids
        return OrderedDict(sorted(albums.items()))

    @staticmethod
    def get_timeline_albums():
        query = (Photo.select()
                 .where(Photo.image_supplier_name.in_(['Weibo', 'Instagram', 'RedBook']))
                 .where(Photo.date_created > pendulum.from_timestamp(0))
                 .order_by(Photo.date_created)
                 .where(~Photo.hidden))
        albums = defaultdict(set)
        for p in query:
            date = pendulum.instance(p.date_created).add(months=2, days=15)
            season = (date.month >= 8) + 1
            album_name = max(f'{date.year}S{season}'[2:], '18S2')

            albums[('timeline', album_name)].add(p.uuid)
        assert sorted(albums.keys()) == list(albums.keys())
        assert sum(len(v) for v in albums.values()) == len(query)
        return albums

    def create_album(self, recreating=True):
        albums = {}
        for a in self.photosdb.album_info:
            if 'Untitled' in a.title:
                continue
            path = tuple(p.title for p in chain(a.folder_list, [a]))
            if path not in albums:
                albums[path] = a
            else:
                console.log(f'Deleting duplicate {path}...')
                alb = self.photoslib.album(uuid=a.uuid)
                self.photoslib.delete_album(alb)

        with get_progress() as progress:
            for alb_path, photo_uuids in progress.track(
                    self.album_info.items(), description='Adding to album...'):
                alb = albums.pop(alb_path, None)
                if alb is not None:
                    album_uuids: set[str] = {p.uuid for p in alb.photos if not (
                        p.intrash or p.hidden)} - self.need_fix
                    protect = 'refresh' in alb.title and len(alb.photos) < 3000
                    if not protect and (unexpected := (album_uuids - photo_uuids)):
                        unexpected_photo = Photo.get_by_id(unexpected.pop())
                        console.log(f'{alb_path}: exists unexpected photo... ')
                        console.log(model_to_dict(unexpected_photo))
                        console.log(f'the unexpectedphoto will added to album'
                                    f':=>{self.photo2album[unexpected_photo]}')
                        if recreating or len(album_uuids) < 2000:
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
                if "uuid" in alb_path:
                    continue
                console.log(f'Deleting {alb_path}...')
                alb = self.photoslib.album(uuid=alb.uuid)
                self.photoslib.delete_album(alb)
