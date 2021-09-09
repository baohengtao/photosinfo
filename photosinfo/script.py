from collections import defaultdict
from pathlib import Path

import exiftool
from imgmeta.helper import get_img_path
from loguru import logger
from tqdm import tqdm

from photosinfo.database import photos_table as table
from photoscript import PhotosLibrary


def weibo_image_tidy(img_dir):
    img_dict = defaultdict(list)
    uuids = []
    with exiftool.ExifTool() as et:
        for img in tqdm(get_img_path(img_dir), desc='tidying...'):
            if not (wb_id := et.get_tag('ImageUniqueID', str(img))):
                img_dict['no_info'].append(img)
            elif x := table.find_one(ImageUniqueID=wb_id):
                img_dict['in_lib'].append(img)
                uuids.append(x['UUID'])
                logger.info(f'{img}:{wb_id}=>{x["Title"]}')
            else:
                img_dict['new'].append(img)

    for folder, imgs in tqdm(img_dict.items(), desc='moving...'):
        for img_path in imgs:
            folder = Path(folder)
            folder.mkdir(exist_ok=True)
            new_img_path = Path(folder) / img_path.name
            if not new_img_path.exists():
                logger.info(f'move {img_path} to {new_img_path}')
                img_path.rename(new_img_path)
    photoslib = PhotosLibrary()
    if uuids:
        photos = photoslib.photos(uuid=uuids)
        photoslib.create_album('in_lib').add(photos)
