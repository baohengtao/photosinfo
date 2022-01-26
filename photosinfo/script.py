import os

import pendulum
from typer import Typer, Option

from photosinfo import console
from photosinfo.model import Photo
from photosinfo.photosinfo import update_table, PhotosDB, PhotosLibrary, add_photo_to_album
import exiftool
from pathlib import Path
from rich.progress import track
app = Typer()


@app.command()
def tidy_photo_in_album(update: bool = Option(False, '--update', '-u')):
    photoslib_path = os.path.expanduser('~/Pictures/照片图库.photoslibrary')
    photosdb = PhotosDB(photoslib_path)
    update_artist()
    if update:
        console.log('update table...')
        update_table(photosdb.photos())
    console.log('add photo to album...')
    photoslib = PhotosLibrary()
    add_photo_to_album(photosdb, photoslib)



@app.command()
def update_artist():
    from sinaspider.model import Artist
    for artist in track(Artist.select(), description='Updating artist...'):
        select_all = Photo.select().where(Photo.image_supplier_id == artist.user_id)
        select_recent = select_all.where(Photo.date_created > pendulum.now().subtract(days=180))
        artist.photos_num = select_all.count()
        artist.recent_num = select_recent.count()
        artist.save()

def _img_in_lib(imgs):
    with exiftool.ExifTool() as et:
        for img in imgs:
            if img.is_dir():
                continue
            unique_id = et.get_tag('XMP:ImageUniqueID', str(img))
            query = Photo.select().where(Photo.image_unique_id == unique_id)
            for p in query.execute():
                yield img, p.uuid
@app.command()
def tidy_img_dir(dir):
    dir = Path(dir)
    imgs = Path(dir).rglob("*")
    d=dict(_img_in_lib(imgs))
    to_dir = dir/'in_lib'
    to_dir.mkdir(exist_ok=True)
    for img in d.keys():
        img.rename(to_dir/img)


