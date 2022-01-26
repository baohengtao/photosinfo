from peewee import Model
from playhouse.postgres_ext import (
    PostgresqlExtDatabase, TextField, DoubleField, CharField,
    DateTimeTZField, BooleanField
)
from sinaspider.model import init_database

database = PostgresqlExtDatabase('imgmeta', autoconnect=True, autorollback=True)
init_database('sinaspider')


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
    blog_title = TextField(column_name='BlogTitle', null=True)
    blog_url = TextField(column_name='BlogURL', null=True)
    live_photo = BooleanField(index=True)
    with_place = BooleanField(index=True)
    favorite = BooleanField(index=True)

    class Meta:
        table_name = 'photo'

    @classmethod
    def column_to_field(cls, column):
        field = cls._meta.columns[column]
        return field.name


database.create_tables([Photo, ])
