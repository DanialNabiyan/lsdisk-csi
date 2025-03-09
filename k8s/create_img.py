from os import environ
from csi_utils import mount_device,create_img,umount_device

disk = environ.get("disk")
size = environ.get("size")
volume_name = environ.get("volume")
mount_device(src=f"/dev/{disk}",dest="/mnt")
create_img(volume_id=volume_name,size=int(size))
umount_device(disk)