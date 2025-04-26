import os
from logger import get_logger
from lsdisk_utils import (
    expand_img,
    find_disk,
    mount_device,
    umount_device,
)
logger = get_logger(__name__)

storagemodel = os.getenv("STORAGE_MODEL")
volume_id = os.getenv("VOLUME_ID")
capacity_range = os.getenv("CAPACITY_RANGE")
mount_dest = os.getenv("MOUNT_DEST")

disks = find_disk(storage_model=storagemodel)
for disk in disks:
    mount_device(src=disk, dest=mount_dest)
    expand = expand_img(volume_id=volume_id, size=capacity_range)
    umount_device(mount_dest)
    if expand:
        logger.info(f"Image {volume_id} extended successfully")
        break
