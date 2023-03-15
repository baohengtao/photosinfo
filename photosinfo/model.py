import pendulum
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

from photosinfo import console

database = PostgresqlExtDatabase(
    'imgmeta', host='localhost', autoconnect=True, autorollback=True)


class BaseModel(Model):
    class Meta:
        database = database

    def __str__(self) -> str:
        return '\n'.join(f'{k}: {v}' for k, v in model_to_dict(self).items() if v)


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
    image_supplier_id = BigIntegerField(
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


database.create_tables([Photo, ])
