import os
from logger import get_logger
from lsdisk_utils import (
    expand_img,
    find_RAID_disks,
    find_disk,
    mount_device,
    umount_device,
)
logger = get_logger(__name__)

storagemodel = os.getenv("STORAGE_MODEL")
volume_id = os.getenv("VOLUME_ID")
capacity_range = os.getenv("CAPACITY_RANGE")
mount_dest = os.getenv("MOUNT_DEST")
disk_type = os.getenv("DISK_TYPE")

if storagemodel.startswith("LOGICAL"):
    disks = find_RAID_disks(storagemodel, disk_type)
else:
    disks = find_disk(storagemodel)
for disk in disks:
    logger.info(f"Found disk: {disk}")
    mount_device(src=f"/dev/{disk}", dest=mount_dest)
    expand = expand_img(volume_id=volume_id, size=int(capacity_range))
    logger.info(f"expand img: {expand}")
    umount_device(mount_dest)
    if expand:
        logger.info(f"Image {volume_id} extended successfully")
        break
