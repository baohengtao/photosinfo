from collections import defaultdict
from typing import Self

import pendulum
import questionary
from osxphotos import PhotoInfo, QueryOptions
from peewee import Model
from photoscript import PhotosLibrary
from playhouse.postgres_ext import (
    ArrayField,
    BigIntegerField,
    BooleanField, CharField,
    DateTimeTZField,
    DoubleField,
    PostgresqlExtDatabase,
    TextField
)
from playhouse.shortcuts import model_to_dict
from rich.prompt import Confirm

from photosinfo import console, get_progress

database = PostgresqlExtDatabase(
    'imgmeta', host='localhost', autoconnect=True, autorollback=True)


class BaseModel(Model):
    class Meta:
        database = database

    def __str__(self) -> str:
        return '\n'.join(f'{k}: {v}' for k, v in model_to_dict(self).items() if v not in ['', None, 0])

    @classmethod
    def get_or_none(cls, *query, **filters) -> Self | None:
        return super().get_or_none(*query, **filters)

    @classmethod
    def get(cls, *query, **filters) -> Self:
        return super().get(*query, **filters)


class Geolocation(BaseModel):
    address = TextField(null=True)
    latitude = DoubleField(null=True)
    longitude = DoubleField(null=True)
    query = TextField(null=True)

    class Meta:
        table_name = 'geolocation'


class Photo(BaseModel):
    uuid = CharField(primary_key=True)
    artist = CharField(column_name='Artist', null=True)
    image_creator_name = CharField(column_name='ImageCreatorName', null=True)
    image_creator_id = CharField(column_name='ImageCreatorID', null=True)
    image_supplier_name = CharField(column_name='ImageSupplierName', null=True)
    image_supplier_id = TextField(
        column_name='ImageSupplierID', null=True)
    image_unique_id = CharField(column_name='ImageUniqueID', null=True)
    series_number = CharField(column_name='SeriesNumber', null=True)
    date_created = DateTimeTZField(column_name='DateCreated', null=True)
    title = CharField(column_name='Title', null=True)
    description = TextField(column_name='Description', null=True)
    album = CharField(column_name='Album', null=True)
    blog_title = TextField(column_name='BlogTitle', null=True)
    blog_url = TextField(column_name='BlogURL', null=True)
    location = TextField(column_name='Location', null=True)
    latitude = DoubleField(column_name='GPSLatitude', null=True)
    longitude = DoubleField(column_name='GPSLongitude', null=True)
    geography = TextField(column_name='Geography', null=True)
    filename = TextField()
    live_photo = BooleanField()
    with_place = BooleanField()
    ismovie = BooleanField(null=True)
    favorite = BooleanField()
    date_added = DateTimeTZField(null=False)
    date = DateTimeTZField(null=False)
    filesize = DoubleField()
    hidden = BooleanField()
    row_created = DateTimeTZField(default=pendulum.now)

    class Meta:
        table_name = 'photo'

    @classmethod
    def info_to_row(cls, p: PhotoInfo) -> dict:
        try:
            meta = p.exiftool.asdict()
        except AttributeError:
            console.log(f'no exiftool=>{p.uuid}', style='warning')
            raise
        if d := meta.get('XMP:DateCreated'):
            meta['XMP:DateCreated'] = pendulum.parse(
                d.removesuffix('+08:00'), tz='local')
        row = {field.name: meta.get(f'XMP:{col}')
               for col, field in cls._meta.columns.items()}
        row.pop('row_created')
        row.update(
            uuid=p.uuid,
            live_photo=p.live_photo,
            with_place=all(p.location),
            favorite=p.favorite,
            date_added=p.date_added,
            filename=p.original_filename,
            filesize=p.original_filesize / (10 ** 6),
            ismovie=p.ismovie,
            hidden=p.hidden,
            date=p.date)
        return row

    @classmethod
    def update_table(cls, photosdb, photoslib: PhotosLibrary, tag_uuid=False):
        photos = photosdb.photos(intrash=False)
        _deleted_count = cls.delete().where(cls.uuid.not_in(
            [p.uuid for p in photos])).execute()
        console.log(f'Delete {_deleted_count} photos')

        with get_progress() as progress:
            process_uuid = {p.uuid for p in photos}
            process_uuid -= {p.uuid for p in cls}
            process_photos = [p for p in photos if p.uuid in process_uuid]
            rows = []
            failed_uuid = []
            new_uuid = []
            for p in progress.track(
                    process_photos, description='Updating table...'):
                try:
                    rows.append(cls.info_to_row(p))
                    new_uuid.append(p.uuid)
                except AttributeError:
                    failed_uuid.append(p.uuid)

            if tag_uuid:
                if query_new_uuid := [p.uuid for p in photosdb.query(
                        QueryOptions(keyword=['new_uuid']))]:
                    for p in photoslib.photos(uuid=query_new_uuid):
                        p.keywords = p.keywords.copy().remove('new_uuid')
                if query_failed_uuid := [p.uuid for p in photosdb.query(
                        QueryOptions(keyword=['failed_uuid']))]:
                    for p in photoslib.photos(uuid=query_failed_uuid):
                        p.keywords = p.keywords.copy().remove('failed_uuid')

                if new_uuid:
                    for p in photoslib.photos(uuid=new_uuid):
                        p.keywords += ['new_uuid']
                if failed_uuid:
                    for p in photoslib.photos(uuid=failed_uuid):
                        p.keywords += ['failed_uuid']

            cls.insert_many(rows).execute()

        favor_uuid = {p.uuid for p in photos if p.favorite}
        favor_uuid -= {p.uuid for p in cls.select().where(cls.favorite)}
        unfavor_uuid = {p.uuid for p in photos if not p.favorite}
        unfavor_uuid -= {p.uuid for p in cls.select().where(~cls.favorite)}
        cls.update(favorite=True).where(cls.uuid.in_(favor_uuid)).execute()
        cls.update(favorite=False).where(
            cls.uuid.in_(unfavor_uuid)).execute()

        hiden_uuid = {p.uuid for p in photos if p.hidden}
        hiden_uuid -= {p.uuid for p in cls.select().where(cls.hidden)}
        unhidden_uuid = {p.uuid for p in photos if not p.hidden}
        unhidden_uuid -= {p.uuid for p in cls.select().where(~cls.hidden)}
        cls.update(hidden=True).where(cls.uuid.in_(hiden_uuid)).execute()
        cls.update(hidden=False).where(
            cls.uuid.in_(unhidden_uuid)).execute()


class Girl(BaseModel):
    username = CharField(primary_key=True)
    sina_name = CharField(null=True, unique=True)
    inst_name = CharField(null=True, unique=True)
    red_name = CharField(null=True, unique=True)
    sina_id = BigIntegerField(null=True, unique=True, index=True)
    inst_id = BigIntegerField(null=True, unique=True, index=True)
    red_id = TextField(null=True, unique=True, index=True)
    sina_num = BigIntegerField(default=0)
    inst_num = BigIntegerField(default=0)
    red_num = BigIntegerField(default=0)
    total_num = BigIntegerField(default=0)
    sina_new = BooleanField(null=True)
    inst_new = BooleanField(null=True)
    red_new = BooleanField(null=True)
    sina_page = TextField(null=True)
    inst_page = TextField(null=True)
    red_page = TextField(null=True)

    folder = TextField(null=True, default='recent')

    _columns = defaultdict(set)
    _nickname = {}

    def get_total_num(self) -> int:
        return self.sina_num + self.inst_num + self.red_num

    def change_username(self, new_name) -> Self:
        if not (new_name := new_name.strip()):
            raise ValueError('new_name is empty')
        if new_name == self.username:
            return self
        GirlSearch.update(username=new_name).where(
            GirlSearch.username == self.username).execute()
        if not (girl := Girl.get_or_none(username=new_name)):
            Girl.update(username=new_name).where(
                Girl.username == self.username).execute()
        else:
            model_dict = model_to_dict(self)
            model_dict.pop('username')
            self.delete_instance()
            for k, v in model_dict.items():
                if k in ['folder', 'total_num'] or v in [None, 0]:
                    continue
                assert getattr(girl, k) is None
                setattr(girl, k, v)
                if k.endswith('_name'):
                    self._nickname[v] = new_name
            girl.save()
        girl = Girl.get_by_id(new_name)
        girl.sync_username()
        return girl

    def sync_username(self):
        from insmeta.model import User as InstUser
        from redbook.model import User as RedbookUser
        from sinaspider.model import User as SinaUser
        models = dict(sina=SinaUser, inst=InstUser, red=RedbookUser)
        for col, Table in models.items():
            if not (user_id := getattr(self, col+'_id')):
                continue
            user = Table.get_by_id(user_id)
            if user.username != self.username:
                console.log(
                    f'{col}: changing {user.username} to {self.username}',
                    style='red bold')
                user.username = self.username
                user.save()
                console.log(user, '\n')

            # nickname = getattr(self, col+'_name')
            # self._nickname[nickname] = self.username

    @classmethod
    def init_cache(cls):
        if cls._columns:
            return
        for raw in cls:
            raw = model_to_dict(raw)
            for k, v in raw.items():
                cls._columns[k].add(v)
                if k.endswith('_name') and v:
                    assert cls._nickname.setdefault(
                        v, raw['username']) == raw['username']

    @classmethod
    def insert_row(cls, row: dict):
        """
        row = {'username': u.username,
            f'{col}_name': u.nickname,
            f'{col}_id': u.id,
            f'{col}_num': u.photos_num,
            f'{col}_page': a.homepage
        }
        """
        cls.init_cache()
        col = row.pop('col')
        id_idx = col+'_id'
        nick_idx = col+'_name'
        username = row['username']
        nickname = row[nick_idx]
        if (id_ := row[id_idx]) not in cls._columns[id_idx]:
            console.log(f"inserting {row}")
            row[f'{col}_new'] = True
            if username in cls._columns['username']:
                cls.update(row).where(cls.username == username).execute()
                assert cls._nickname.setdefault(
                    nickname, username) == username
            elif u := (cls._nickname.get(nickname)
                       or cls._nickname.get(username)):
                assert u != username
                console.log(f'find {u} with nickname {nickname}')
                console.log(Girl.get_by_id(u))
                if not Confirm.ask(f'change {username} to {u}?', default=True):
                    raise ValueError(f'inserting {row} failed')
                cls._nickname[nickname] = u
                row['username'] = username = u
                cls.update(row).where(cls.username == username).execute()
                cls.get(username=username).sync_username()
            else:
                cls._columns['username'].add(username)
                row['folder'] = 'recent'
                cls.insert(row).execute()
                assert cls._nickname.setdefault(
                    nickname, username) == username
            girl = cls.get_by_id(username)
        else:
            girl: cls = cls.get(**{id_idx: id_})
            for idx in ['name', 'num', 'page']:
                idx = col+'_'+idx
                if getattr(girl, idx) != row[idx]:
                    setattr(girl, idx, row[idx])
                    girl.save()
            if not getattr(girl, f'{col}_num'):
                if not getattr(girl, f'{col}_new'):
                    setattr(girl, f'{col}_new', True)
                    girl.save()
            assert not girl.is_dirty()
            if girl.username != username:
                console.print(
                    "which username would want keep ?")
                console.log(girl)
                console.log(row)
                goldname = questionary.select("choose username:", choices=[
                    girl.username, username]).unsafe_ask()
                if goldname == girl.username:
                    girl.sync_username()
                else:
                    cls._columns['username'].add(username)
                    cls._columns['username'].remove(girl.username)
                    console.log(f'changing {girl.username} to {username}')
                    girl = girl.change_username(username)
                    console.log(girl)
        if (total_num := girl.get_total_num()) != girl.total_num:
            girl.total_num = total_num
            girl.save()

    @classmethod
    def update_table(cls, prompt=False):
        from insmeta.model import Artist as InstArtist
        from insmeta.model import User as InstUser
        from redbook.model import Artist as RedArtist
        from redbook.model import User as RedUser
        from sinaspider.model import Artist as SinaArtist
        from sinaspider.model import User as SinaUser
        cls.update_artist()
        models = {'sina': (SinaArtist, SinaUser),
                  'inst': (InstArtist, InstUser),
                  'red': (RedArtist, RedUser)}
        for col, (Artist, User) in models.items():
            rows = {}
            rows_redirect = {}
            for a in Artist.select(Artist, User).join(User):
                u = a.user
                row = {
                    'col': col,
                    'username': u.username,
                    f'{col}_name': u.nickname.strip('-_ ').lower(),
                    f'{col}_id': u.id,
                    f'{col}_num': a.photos_num,
                    f'{col}_page': a.homepage
                }
                if getattr(u, 'redirect', None):
                    rows_redirect[u.redirect] = row
                else:
                    rows[u.id] = row
            for uid, row in rows_redirect.items():
                rows[uid][f'{col}_num'] += row[f'{col}_num']
                assert rows[uid]['username'] == row['username']
            for row in rows.values():
                cls.insert_row(row)
            for girl in cls:
                if not (col_id := getattr(girl, f'{col}_id')):
                    continue
                if col_id not in rows:
                    if getattr(girl, f'{col}_num'):
                        setattr(girl, f'{col}_num', 0)
                        girl.total_num = girl.get_total_num()
                        girl.save()
                    if not getattr(girl, f'{col}_new'):
                        setattr(girl, f'{col}_new', True)
                        girl.save()
        cls._validate()
        if prompt:
            cls._clean()

    @classmethod
    def _clean(cls):
        from insmeta.model import Artist as InstArtist
        from redbook.model import Artist as RedArtist
        from sinaspider.model import Artist as SinaArtist
        models = {'sina': SinaArtist, 'inst': InstArtist, 'red': RedArtist}
        clean_single = Confirm.ask(
            'clean girl with 0 photos and only on account?', default=False)
        for girl in cls.select().where(cls.total_num == 0):
            accounts = [girl.sina_id, girl.inst_id, girl.red_id]
            if sum(bool(x) for x in accounts) > 1:
                console.log(girl)
                if not Confirm.ask(f'delete {girl.username}?', default=True):
                    continue
            elif not clean_single:
                continue
            for col, Table in models.items():
                if uid := getattr(girl, f'{col}_id'):
                    if artist := Table.get_or_none(user_id=uid):
                        console.log(f'deleting {artist.username}...')
                        console.log(artist, '\n')
                        artist.delete_instance()
            girl.delete_instance()
        for girl in Girl:
            girl_dict = model_to_dict(girl)
            for col in ['sina', 'inst', 'red']:
                new_idx = f'{col}_new'
                num_idx = f'{col}_num'
                if girl_dict[new_idx] and (num := girl_dict[num_idx]):
                    console.log(girl)
                    if Confirm.ask(
                        f'{col} has {num} photos, change new_idx to False?',
                        default=True
                    ):
                        setattr(girl, new_idx, False)
                        girl.save()

    @classmethod
    def _validate(cls):
        ids = set()
        for girl in cls:
            for col in ['sina', 'inst', 'red']:
                if id_ := getattr(girl, col+'_id'):
                    id_ = str(id_)
                    assert id_ not in ids
                    ids.add(id_)

        for girl in cls:
            girl: cls
            assert girl.total_num == girl.get_total_num()
            girl_dict = model_to_dict(girl)
            for col in ['sina', 'inst', 'red']:
                id_idx = col+'_id'
                num_idx = col+'_num'
                new_idx = col+'_new'
                page_idx = col+'_page'
                if girl_dict[id_idx] is None:
                    assert girl_dict[num_idx] == 0
                    assert girl_dict[new_idx] is None
                    assert girl_dict[page_idx] is None
                else:
                    assert girl_dict[page_idx] is not None
                    assert (is_new := girl_dict[new_idx]) is not None
                    assert is_new or girl_dict[num_idx]

    @classmethod
    def update_artist(cls):
        from insmeta.model import Artist as InsArtist
        from redbook.model import Artist as RedArtist
        from sinaspider.model import Artist as SinaArtist
        from twimeta.model import Artist as TwiArtist
        kls_dict = {
            'Weibo': SinaArtist,
            'Instagram': InsArtist,
            'Twitter': TwiArtist,
            'RedBook': RedArtist,
        }
        collector = defaultdict(lambda: defaultdict(int))
        for p in Photo:
            supplier = p.image_supplier_name
            uid = p.image_supplier_id or p.image_creator_name
            if supplier and uid:
                if not uid.isdigit():
                    assert supplier in ['Twitter', 'RedBook']
                assert p.artist
                collector[supplier][uid] += 1
        for uid in (set(collector['WeiboLiked']) & set(collector['Weibo'])):
            a = SinaArtist.from_id(uid)
            console.log(
                f'Found {a.username} still in WeiboLiked', style='warning')

        for supplier, kls in kls_dict.items():
            uids = collector[supplier].copy()
            rows = list(kls)
            to_extend = set(uids) - {str(row.user_id) for row in rows}
            rows.extend(kls.from_id(uid) for uid in to_extend)
            for row in rows:
                row.photos_num = uids[str(row.user_id)]
                row.save()


class GirlSearch(BaseModel):
    username = CharField()
    col = CharField()
    user_id = TextField()
    nickname = CharField()
    search_for = CharField()
    searched = BooleanField(default=False)
    search_url = TextField(null=True)
    homepages = ArrayField(TextField, null=True)
    folder = TextField(null=True)

    class Meta:
        indexes = (
            (('nickname', 'search_for'), True),
        )

    @classmethod
    def _validate(cls):
        usernames = {s.username for s in cls}
        girlnames = {g.username for g in Girl}
        assert usernames.issubset(girlnames)

    @classmethod
    def add_querys(cls):
        from photosinfo.helper import pinyinfy
        cls._validate()
        for girl in Girl:
            girl_dict = model_to_dict(girl)
            accounts = {}
            missed = []
            homepages = []
            for col in ['sina', 'inst', 'red']:
                nickname = girl_dict[col+'_name']
                user_id = girl_dict[col+'_id']
                homepage = girl_dict[col+'_page']
                assert (nickname is None) is (
                    user_id is None) is (homepage is None)
                if user_id is None:
                    missed.append(col)
                    continue
                homepages.append(homepage)
                accounts[col] = (nickname, user_id)
            accounts['username'] = (girl.username.lower(), 'from_username')

            for search_for in accounts:
                while model := cls.get_or_none(
                    search_for=search_for,
                    username=girl.username
                ):
                    model.delete_instance()

            for col, (nickname, user_id) in accounts.items():
                row = {
                    'col': col,
                    'user_id': user_id,
                    'username': girl.username,
                    'homepages': homepages,
                    'folder': girl.folder
                }
                for search_for in missed:
                    r = dict(search_for=search_for,
                             nickname=nickname)
                    if model := cls.get_or_none(**r):
                        assert model.username == girl.username
                        if model.folder != girl.folder:
                            model.folder = girl.folder
                            model.save()
                        continue
                    row |= r
                    if search_for == 'sina':
                        row['search_url'] = f'https://s.weibo.com/user?q={nickname}&Refer=weibo_user'
                    elif search_for == 'red':
                        row['search_url'] = f'https://www.xiaohongshu.com/search_result?keyword={nickname}'
                    else:
                        assert search_for == 'inst'
                        row['search_url'] = nickname
                        if nickname == girl.username:
                            if pinyin := pinyinfy(girl.username):
                                row['search_url'] += ' ' + pinyin

                    console.log(f'inserting {row}...')
                    cls.insert(row).execute()
        cls._validate()


database.create_tables([Photo, Girl, GirlSearch])
