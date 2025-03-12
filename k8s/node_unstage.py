from pathlib import Path
from os import environ

from csi_utils import detach_loops, find_disk, mount_device, umount_device
from utils import be_absent, get_storageclass_from_pv, get_storageclass_storagemodel_param


volume = environ.get("volume")
storageclass = get_storageclass_from_pv(volume)
print(storageclass)
storagemodel = get_storageclass_storagemodel_param(storageclass_name=storageclass)
print(storagemodel)
disk = find_disk(storage_model=storagemodel)
print(disk)
mount_device(src=f"/dev/{disk}",dest="/mnt")
staging_target_path = environ.get("staging_target_path")
img_file = Path(f"/mnt/{volume}/disk.img")
umount_device(staging_target_path)
be_absent(staging_target_path)
detach_loops(img_file)