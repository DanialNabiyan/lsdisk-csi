from pathlib import Path
from csi_utils import attach_loop, mount_device,find_disk
from utils import get_storageclass_from_pv,get_storageclass_storagemodel_param
from os import environ

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
loop_file = attach_loop(img_file)
print(f"loop_file: {loop_file}")
print(f"staging_path: {staging_target_path}")
mount_device(src=loop_file,dest=staging_target_path)