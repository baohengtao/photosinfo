from sqlalchemy import Text, Boolean
import dataset
DATABASE = 'imgmeta'
Photo_TABLE = 'photos'

database_url = 'photogresql://localhost/%s' % DATABASE
database = dataset.connect(database_url)
photos_table = database.create_table(
    Photo_TABLE,
    primary_id='uuid',
    primary_type=Text,
    primary_increment=False)

photos_table.create_column('live_photo', Boolean)
photos_table.create_column('with_place', Boolean)
photos_table.create_column('favorite', Boolean)

columns = ['Location', 'Description', 'Title',
           'ImageUniqueID', 'DateCreated', 'ImageCreatorID',
           'ImageCreatorName', 'ImageSupplierID', 'SeriesNumber',
           'ImageSupplierName', 'BlogURL', 'Geography', 'Artist']
for column in columns:
    photos_table.create_column(column, Text)
