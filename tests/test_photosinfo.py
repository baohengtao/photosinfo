from photosinfo import __version__
import pytest
from photosinfo.model import PhotosDB, update_table
import os

def test_version():
    assert __version__ == '0.2.0'



@pytest.fixture(scope='session')
def photosdb():
    photoslib_path = os.path.expanduser('~/Pictures/照片图库.photoslibrary')
    return PhotosDB(photoslib_path)

def test_update_table(photosdb: PhotosDB):
    photos = photosdb.photos()
    p = list(photos)[:3]
    update_table(p)


