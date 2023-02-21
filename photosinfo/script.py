from osxphotos import PhotosDB
from photoscript import PhotosLibrary
from typer import Typer

from photosinfo import console
from photosinfo.photosinfo import (
    add_photo_to_album,
    update_artist,
    update_table
)

app = Typer(
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=False
)


@app.command()
def tidy_photo_in_album(new_artist: bool = False, sina_clean: bool = False):
    photosdb = PhotosDB()
    console.log('update table...')
    update_table(photosdb)
    update_artist(new_artist)
    console.log('add photo to album...')
    photoslib = PhotosLibrary()
    add_photo_to_album(photosdb, photoslib)
    if sina_clean:
        sina_db_clean()


def sina_db_clean():
    import questionary
    from sinaspider.model import Artist, User, UserConfig, Weibo

    from photosinfo.model import Photo
    if not questionary.confirm('Have you backup database to rpi?').ask():
        console.log('Backup first, bye!')
        return
    if not questionary.confirm('Have you put all photos to Photos.app?').ask():
        console.log('put them to Photos.app first, bye!')
        return
    photos = (Photo.select()
              .where(Photo.image_supplier_name == "Weibo")
              .where(Photo.image_unique_id.is_null(False)))
    photo_bids = {p.image_unique_id for p in photos}
    console.log(f'{len(photo_bids)} weibos in photos.app\n'
                f'{len(Weibo)} weibos in sina database')
    del_count = Weibo.delete().where(Weibo.bid.not_in(photo_bids)).execute()
    console.log(f'{del_count} weibos have been deleted\n'
                f'{len(Weibo)} weibos left in sina database')
    uids = {u.user_id for u in UserConfig} | {u.user_id for u in Artist}
    del_count = User.delete().where(User.id.not_in(uids)).execute()
    console.log(f'{del_count} users have been deleted')
    console.log('Done!')
