import pendulum
from osxphotos import PhotoInfo
from peewee import Model
from playhouse.postgres_ext import (
    PostgresqlExtDatabase, TextField, DoubleField, CharField,
    DateTimeTZField, BooleanField
)
from photosinfo import console

database = PostgresqlExtDatabase(
    'imgmeta', host='localhost', autoconnect=True, autorollback=True)


class BaseModel(Model):
    class Meta:
        database = database


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
    image_supplier_id = CharField(column_name='ImageSupplierID', null=True)
    image_unique_id = CharField(column_name='ImageUniqueID', null=True)
    series_number = CharField(column_name='SeriesNumber', null=True)
    date_created = DateTimeTZField(column_name='DateCreated', null=True)
    album = CharField(column_name='Album', null=True)
    blog_title = TextField(column_name='BlogTitle', null=True)
    blog_url = TextField(column_name='BlogURL', null=True)
    live_photo = BooleanField(index=True)
    with_place = BooleanField(index=True)
    ismovie = BooleanField(null=True)
    favorite = BooleanField(index=True)
    date_added = DateTimeTZField(null=False)
    filesize = DoubleField()

    class Meta:
        table_name = 'photo'

    @classmethod
    def column_to_field(cls, column):
        field = cls._meta.columns[column]
        return field.name

    @classmethod
    def add_to_db(cls, p: PhotoInfo):
        try:
            meta = p.exiftool.asdict()
        except AttributeError:
            console.log(f'no exiftool=>{p.uuid}', style='warning')
            return

        row = {Photo.column_to_field(k): meta.get(
            'XMP:%s' % k) for k in Photo._meta.columns}
        if d := row.get('date_created'):
            row['date_created'] = pendulum.parse(d, strict=False)
        photo = Photo(**row)
        photo.uuid = p.uuid
        photo.live_photo = p.live_photo
        photo.with_place = all(p.location)
        photo.favorite = p.favorite
        photo.date_added = p.date_added
        photo.filesize = p.original_filesize / (10 ** 6)
        photo.ismovie = p.ismovie
        photo.save(force_insert=True)


database.create_tables([Photo, ])
