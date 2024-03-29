
from collections import Counter, defaultdict

import pendulum

from photosinfo import get_progress
from photosinfo.model import Photo


def update_table(photosdb):
    photos = photosdb.photos()
    Photo.delete().where(Photo.uuid.not_in(
        [p.uuid for p in photos])).execute()

    with get_progress() as progress:
        process_uuid = {p.uuid for p in photos}
        process_uuid -= {p.uuid for p in Photo.select()}
        process_photos = [p for p in photos if p.uuid in process_uuid]
        rows = []
        for p in progress.track(
                process_photos, description='Updating table...'):
            rows.append(Photo.info_to_row(p))
        Photo.insert_many(rows).execute()

    favor_uuid = {p.uuid for p in photos if p.favorite}
    favor_uuid -= {p.uuid for p in Photo.select().where(Photo.favorite)}
    unfavor_uuid = {p.uuid for p in photos if not p.favorite}
    unfavor_uuid -= {p.uuid for p in Photo.select().where(~Photo.favorite)}
    Photo.update(favorite=True).where(Photo.uuid.in_(favor_uuid)).execute()
    Photo.update(favorite=False).where(Photo.uuid.in_(unfavor_uuid)).execute()


def update_artist(new_artist: bool = False):
    from insmeta.model import Artist as InsArtist
    from playhouse.shortcuts import update_model_from_dict
    from sinaspider.model import Artist as SinaArtist
    from twimeta.model import Artist as TwiArtist
    kls_dict = {
        'Weibo': SinaArtist,
        'Instagram': InsArtist,
        'Twitter': TwiArtist
    }
    # collections of uids
    uids_info = defaultdict(set)
    # counter of username
    username_info = defaultdict(
        lambda: Counter(photos_num=0, recent_num=0, favor_num=0))
    for p in Photo:
        supplier = p.image_supplier_name
        uid = p.image_supplier_id or p.image_creator_name
        if supplier and uid:
            assert isinstance(uid, int) == (supplier != 'Twitter')
            assert p.artist
            update = {'photos_num'}
            if p.date_added > pendulum.now().subtract(days=180):
                update.add('recent_num')
            if p.favorite:
                update.add('favor_num')
            username_info[p.artist].update(update)
            uids_info[supplier].add(uid)

    for supplier, kls in kls_dict.items():
        uids = uids_info[supplier].copy()
        rows = list(kls)
        for row in rows:
            if row.user_id in uids:
                uids.remove(row.user_id)
            else:
                assert row.username not in username_info, (
                    row.username, row.user_id)
        rows.extend(kls.from_id(uid) for uid in uids)
        for row in rows:
            stast = username_info[row.username]
            update_model_from_dict(row, stast)
            row.save()
        if new_artist:
            ids = {row.user_id for row in rows if row.folder == 'new'}
            ids &= uids_info[supplier]
            for id_ in ids:
                artist = kls.from_id(id_, update=True)
                artist.folder = 'recent'
                artist.save()
