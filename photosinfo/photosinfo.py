import math
from collections import OrderedDict, defaultdict
from itertools import chain

import pendulum
from aweme.model import Artist as AwemeArtist
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
    'redbook': RedArtist,
    'aweme': AwemeArtist
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
        assert supplier not in ['weibosaved', 'weibosavedfail']
        if supplier == 'weiboliked':
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
                folder = ('weibosaved', "tbd", album)
            elif supplier == 'weiboliked':
                folder = ('weiboliked', None, '_'.join((liked_by, album)))
            else:
                folder = ('weiboliked', None, album)
            for p in photos:
                self.photo2album[p] = folder
        elif supplier == 'twitter':
            artist = TwiArtist.from_id(uid)
            album = 'small' if len(photos) <= 32 else artist.username
            for p in photos:
                if p.artist != artist.username:
                    self.photo2album[p] = ('福利', None, 'problem')
                    self.need_fix.add(p.uuid)
                else:
                    self.photo2album[p] = ('福利', None, album)
                self.keywords_info[supplier] |= {p.uuid for p in photos}

        elif supplier not in kls_dict:
            assert uid is None
            for p in photos:
                album = p.album or p.artist or 'no_artist'
                if album == 'WANIMALTumblr':
                    album = 'WANIMAL'
                self.photo2album[p] = (supplier, None, album)
        elif uid is None:
            assert supplier == 'weibo'
            for p in photos:
                self.photo2album[p] = ('wechat', 'weibo', p.artist)
        else:
            username = kls_dict[supplier].from_id(uid).username
            girl: Girl = Girl.get_by_id(username)
            first_folder = girl.folder_path

            SMALL_NUMBER = 32
            if 'recent' in first_folder:
                SMALL_NUMBER = 0
            elif 'del' in first_folder:
                SMALL_NUMBER = 0
            elif 'super' in first_folder:
                SMALL_NUMBER = 16
            elif 'ins' in first_folder:
                SMALL_NUMBER = 16
            album = 'small' if girl.total_num <= SMALL_NUMBER else username

            self.keywords_info[supplier] |= {p.uuid for p in photos}

            for p in photos:
                if p.artist != username:
                    self.photo2album[p] = (first_folder, None, 'problem')
                    self.need_fix.add(p.uuid)
                else:
                    self.photo2album[p] = (first_folder, None, album)

    def get_album_info(self) -> OrderedDict[tuple, set[str]]:
        album_info: dict[tuple, set[str]] = defaultdict(set)
        for p, (supplier, sec_folder, album) in self.photo2album.items():
            folder = (supplier, sec_folder) if sec_folder else (supplier,)
            album_info[folder + (album,)].add(p.uuid)
            if sec_folder and (sec_folder == 'super'
                               or sec_folder.startswith('recent')):
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
        album_info |= get_timeline_albums()
        album_info |= get_dup_new_albums()
        album_info |= get_dup_check_albums()
        album_info |= self.locked_user_albums()

        return album_info

    def locked_user_albums(self):
        albums = {}
        for a in self.photosdb.album_info:
            if 'Untitled' in a.title:
                continue
            if 'favor' in a.title:
                continue
            path = tuple(p.title for p in chain(a.folder_list, [a]))
            if path[0] != 'locked.user':
                continue
            _, username = path
            albums[path] = {p.uuid for p in Photo.select().where(
                Photo.artist.in_([username]))}
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

        for alb_path, photo_uuids in self.album_info.items():
            alb = albums.pop(alb_path, None)
            if alb is not None:
                album_uuids: set[str] = {p.uuid for p in alb.photos if not (
                    p.intrash or p.hidden)} - self.need_fix
                protect = ('refresh' in alb.title and len(
                    alb.photos) < 3000) or ('fav' in alb.title)
                if not protect and (unexpected := (album_uuids - photo_uuids)):
                    unexpected_photo = Photo.get_by_id(
                        next(iter(unexpected)))
                    console.log(f'{alb_path}: exists unexpected photo... ')
                    console.log(model_to_dict(unexpected_photo))
                    console.log(f'the unexpectedphoto will added to album'
                                f':=>{self.photo2album[unexpected_photo]}')
                    if len(photo_uuids) > 5000 and len(unexpected) < 500:
                        console.log(
                            f'tagging unexpected photo on {alb_path}...',
                            style='warning')
                        self.keywords_info['unexpected'] |= unexpected
                    elif recreating or len(photo_uuids) < 2000:
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

        for alb_path, alb in albums.items():
            path_str = "".join(alb_path).lower()
            assert "untitled" not in path_str
            if "locked" in path_str:
                console.log(f"skip {alb_path}")
                continue
            console.log(f'Deleting {alb_path}...')
            alb = self.photoslib.album(uuid=alb.uuid)
            self.photoslib.delete_album(alb)


def get_dup_check(checkpoint) -> list[str]:
    start, end = checkpoint.subtract(days=15), checkpoint.add(months=1)
    photos = Photo.select().where(Photo.date_created.between(start, end))
    res = defaultdict(set)
    for p in photos:
        if p.image_supplier_name == 'WeiboLiked':
            continue
        if not p.filepath.endswith('.mp4'):
            res[p.artist].add(p.image_supplier_name)
    artists = {k for k, v in res.items() if len(v) > 1}
    return {p.uuid for p in photos if p.artist in artists}


def get_dup_check_albums():
    albums = {}
    now = pendulum.now().start_of('month')
    all_uuids = set()
    for i in range(3):
        checkpoint = now.subtract(months=i)
        name = f'dup_check_{checkpoint:%y_%m}'
        uuids = get_dup_check(checkpoint)
        albums[('locked.dup',  'check', name)] = uuids
        all_uuids |= uuids
    albums[('locked.dup', 'check', 'all')] = all_uuids
    return albums


def get_dup_new_albums() -> OrderedDict[tuple, set[str]]:
    albums = defaultdict(set)
    collector = defaultdict(lambda: defaultdict(set))
    for p in Photo:
        if p.image_supplier_name == 'WeiboLiked':
            continue
        collector[p.artist][p.image_supplier_name].add(p.uuid)

    for girl in Girl.select().where(
            Girl.sina_new | Girl.inst_new | Girl.red_new | Girl.awe_new):
        if len(co := collector.get(girl.username, {})) <= 1:
            continue
        cmp = {'Weibo': girl.sina_new,
               'Instagram': girl.inst_new,
               'RedBook': girl.red_new,
               'Aweme': girl.awe_new
               }
        cmp = {k for k, v in cmp.items() if v}
        if not (cmp & set(co)):
            continue
        for uuids in co.values():
            albums[('dup_new', girl.username)] |= uuids

    albums = OrderedDict(sorted(albums.items(), reverse=True))
    if len(albums) > 1:
        albums[('dup_new', 'all')] = {
            p for v in albums.values() for p in v}
    return albums


def get_timeline_albums():
    query = (Photo.select()
             .where(Photo.image_supplier_name.in_([
                    'Weibo', 'Instagram', 'RedBook', 'Aweme']))
             .where(Photo.date_created > pendulum.from_timestamp(0))
             .order_by(Photo.date_created)
             .where(~Photo.hidden))
    albums = defaultdict(set)
    for p in query:
        date = pendulum.instance(p.date_created).add(months=2, days=15)
        season = (date.month >= 8) + 1
        album_name = max(f'{date.year}S{season}'[2:], '18S2')
        fav_name = max(album_name+'_fav', '20S1_fav')

        albums[('timeline', album_name)].add(p.uuid)
        if p.favorite:
            albums[('timeline', fav_name)].add(p.uuid)
    return albums
