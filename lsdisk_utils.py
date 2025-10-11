import json
import os
from pathlib import Path
import shutil
from utils import run, run_out
from logger import get_logger
from constance.config import MOUNT_DEST, IMAGE_NAME

logger = get_logger(__name__)
    

def find_disk(storage_model):
    output = run_out("lsblk -o MODEL,NAME -d").stdout.decode()
    lines = output.strip().split("\n")[1:]
    result = {}
    for line in lines:
        parts = line.strip().split(None, 1)
        if len(parts) < 2:
            continue
        model = parts[0]
        device_name = parts[1]
        if model not in result:
            result[model] = []
        result[model].append(device_name)
    return result.get(storage_model, [])


def find_RAID_disks(storage_model, disk_type):
    disk_type_number = if disk_type == "HDD" else 0
    output = run_out("lsblk -o MODEL,NAME,ROTA -d").stdout.decode()
    lines = output.strip().split("\n")[1:]
    result = {}
    for line in lines:
        parts = line.strip().split(None, 2)
        if len(parts) < 3:
            continue
        model = parts[0]
        device_name = parts[1]
        dtype = parts[2]
        if model not in result:
            result[model] = []        
        if dtype == disk_type_number:
            result[model].append(device_name)
    return result.get(storage_model, [])


def get_device_with_most_free_space(devicesو full_disk):
    max_free_space = 0
    device_with_most_space = None

    for device in devices:
        device_path = f"/dev/{device}"
        try:
            path = f"{MOUNT_DEST}/{device}"
            mount_device(src=device_path, dest=path)
            usage = shutil.disk_usage(path)
            free_space = usage.free
            if full_disk.lower() == "true" and free_space > max_free_space and usage.total == free_space:
                max_free_space = free_space
                device_with_most_space = device
            elif full_disk.lower() != "true" free_space > max_free_space:
                max_free_space = free_space
                device_with_most_space = device
            umount_device(dest=path)
        except FileNotFoundError:
            logger.warning(f"Device {device_path} not found or inaccessible.")
        except Exception as e:
            logger.error(f"Error checking free space for device {device_path}: {e}")
    if device_with_most_space is None:
        logger.error("No valid devices found with free space.")
        return ""
    return device_with_most_space


def create_img(path, size):
    path = Path(path)
    if not path.exists():
        path.mkdir()
    img_file = Path(f"{path}/{IMAGE_NAME}")
    if img_file.is_file():
        return
    run(f"truncate -s {size} {img_file}")
    run(f"mkfs.ext4 {img_file}")
    if img_file.is_file():
        logger.info(f"img file: {img_file} is created")
        return True
    else:
        logger.error(f"img file: {img_file} is not created")
        return False


def check_mounted(dest):
    is_mounted = run_out(f"mount | grep {dest}").stdout.decode()
    return bool(is_mounted)

def find_fstype(src):
    return run_out(f"blkid -o value -s TYPE {src}").stdout.decode().strip()

def mount_device(src, dest):
    src = Path(src)
    dest = Path(dest)
    if not dest.exists():
        dest.mkdir(exist_ok=True)
    if src.exists() and dest.exists():
        if not check_mounted(dest):
            fs_type = find_fstype(src)
            if fs_type in ["xfs", "ext4"]:
                run(f"mount {src} {dest}")
            elif fs_type == "":
                run(f"mkfs.xfs -f {src}")
                run(f"mount {src} {dest}")
            else:
                raise TypeError("Only FsType xfs and ext4 valid!")
                

def mount_bind(src, dest):
    src = Path(src)
    dest = Path(dest)
    if src.exists():
        dest.mkdir(parents=True, exist_ok=True)
        run(f"mount --bind {src} {dest}")


def umount_device(dest):
    if check_mounted(dest):
        run(f"umount -l {dest}")


def expand_img(volume_id, size):
    img_path = Path(f"{MOUNT_DEST}/{volume_id}/{IMAGE_NAME}")
    if img_path.exists():
        file_size = os.path.getsize(img_path)
        if size > file_size:
            run(f"truncate -s {size} {img_path}")
            return True
        else:
            raise Exception(
                f"Image size {file_size} is already larger than requested size {size}."
            )
    else:
        return False


def attach_loop(file_path: str) -> str:
    def get_next_loop_device() -> str:
        loop_device = run_out(f"losetup -f").stdout.decode().strip()
        if not Path(loop_device).exists():
            loop_id = loop_device.replace("/dev/loop", "")
            run(f"mknod {loop_device} b 7 {loop_id}")
        return loop_device

    while True:
        attached_devices = attached_loops_dev(file_path)
        if len(attached_devices) > 0:
            return attached_devices[0]

        get_next_loop_device()
        run(f"losetup --direct-io=on -f {file_path}")


def attached_loops_dev(file: str) -> [str]:
    out = run_out(f"losetup -j {file}").stdout.decode()
    lines = out.splitlines()
    devs = [line.split(":", 1)[0] for line in lines]
    return devs


def detach_loops(file) -> None:
    devs = attached_loops_dev(file)
    for dev in devs:
        run(f"losetup -d {dev}")


def find_loop_from_path(path):
    res = run_out(
        f"findmnt --json --first-only --nofsroot --mountpoint {path}"
    )
    if res.returncode != 0:
        return None
    data = json.loads(res.stdout.decode().strip())
    return data["filesystems"][0]["source"]


def path_stats(path):
    fs_stat = os.statvfs(path)
    return {
        "fs_size": fs_stat.f_frsize * fs_stat.f_blocks,
        "fs_avail": fs_stat.f_frsize * fs_stat.f_bavail,
        "fs_files": fs_stat.f_files,
        "fs_files_avail": fs_stat.f_favail,
    }

def extend_fs(path):
    path = Path(path).resolve()
    fstype = find_fstype(path)
    if fstype == "ext4":
        run(f"resize2fs {path}")
    elif fstype == "xfs":
        run(f"xfs_growfs -d {path}")
    else:
        raise Exception(f"Unsupported fsType: {fstype}")
