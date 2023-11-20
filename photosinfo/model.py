from collections import defaultdict
from typing import Self

import pendulum
import questionary
from osxphotos import PhotoInfo
from peewee import Model
from playhouse.postgres_ext import (
    BigIntegerField,
    BooleanField, CharField,
    DateTimeTZField,
    DoubleField,
    PostgresqlExtDatabase,
    TextField
)
from playhouse.shortcuts import model_to_dict
from rich.prompt import Confirm

from photosinfo import console

database = PostgresqlExtDatabase(
    'imgmeta', host='localhost', autoconnect=True, autorollback=True)


class BaseModel(Model):
    class Meta:
        database = database

    def __str__(self) -> str:
        return '\n'.join(f'{k}: {v}' for k, v in model_to_dict(self).items() if v)

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


class Girl(BaseModel):
    username = CharField(primary_key=True)
    sina_name = CharField(null=True, unique=True)
    inst_name = CharField(null=True, unique=True)
    red_name = CharField(null=True, unique=True)
    sina_id = BigIntegerField(null=True, unique=True, index=True)
    inst_id = BigIntegerField(null=True, unique=True, index=True)
    red_id = TextField(null=True, unique=True, index=True)
    photos_num = BigIntegerField(default=0)
    recent_num = BigIntegerField(default=0)
    favor_num = BigIntegerField(default=0)

    _columns = defaultdict(set)
    _nickname = {}

    def change_username(self, new_name) -> Self:
        if not (new_name := new_name.strip()):
            raise ValueError('new_name is empty')
        if new_name == self.username:
            return self
        if not (girl := Girl.get_or_none(username=new_name)):
            Girl.update(username=new_name).where(
                Girl.username == self.username).execute()
        else:
            model_dict = model_to_dict(self)
            model_dict.pop('username')
            self.delete_instance()
            for k, v in model_dict.items():
                if k.endswith('_num') or v is None:
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
                f'{col}_id': u.id}
        """
        cls.init_cache()
        col = row.pop('col')
        id_idx = col+'_id'
        nick_idx = col+'_name'
        username = row['username']
        nickname = row[nick_idx]
        if (id_ := row[id_idx]) not in cls._columns[id_idx]:
            console.log(f"inserting {row}")
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
                cls.insert(row).execute()
                assert cls._nickname.setdefault(
                    nickname, username) == username
        else:
            girl: cls = cls.get(**{id_idx: id_})
            if getattr(girl, nick_idx) != nickname:
                setattr(girl, nick_idx, nickname)
                girl.save()
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

    @classmethod
    def update_table(cls):
        from insmeta.model import Artist as InstArtist
        from insmeta.model import User as InstUser
        from redbook.model import Artist as RedArtist
        from redbook.model import User as RedUser
        from sinaspider.model import Artist as SinaArtist
        from sinaspider.model import User as SinaUser
        models = {'sina': (SinaArtist, SinaUser),
                  'inst': (InstArtist, InstUser),
                  'red': (RedArtist, RedUser)}
        for col, (Artist, User) in models.items():
            user_ids = {a.user_id for a in Artist}
            for u in User:
                if u.id not in user_ids:
                    continue
                if getattr(u, 'redirect', None):
                    continue
                row = {
                    'col': col,
                    'username': u.username,
                    f'{col}_name': u.nickname.strip('-_ '),
                    f'{col}_id': u.id}
                cls.insert_row(row)


database.create_tables([Photo, Girl])
