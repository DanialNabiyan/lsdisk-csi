import os
from lsdisk_utils import (
    expand_img,
    find_disk,
    get_device_with_most_free_space,
    mount_device,
    umount_device,
)

storagemodel = os.getenv("STORAGE_MODEL")
volume_id = os.getenv("VOLUME_ID")
capacity_range = os.getenv("CAPACITY_RANGE")
mount_dest = os.getenv("MOUNT_DEST")

disks = find_disk(storage_model=storagemodel)
disk = (
    get_device_with_most_free_space(disks)
    if len(disks) > 1
    else disks[0] if disks else ""
)
if disk != "":
    mount_device(src=disk, dest=mount_dest)
    expand_img(volume_id=volume_id, size=capacity_range)
    umount_device(mount_dest)
else:
    raise Exception("No disk found to extend the image")
