import os
from pathlib import Path
from utils import checkoutput, run, run_out
from logger import get_logger

logger = get_logger(__name__)


def find_disk(storage_model):
    output = run("lsblk -o MODEL,NAME -d").stdout.decode()
    lines = output.strip().split("\n")[1:]
    result = {}
    for line in lines:
        parts = line.strip().split(None, 1)
        model = parts[0]
        device_name = parts[1] if len(parts) > 1 else ""
        result[model] = device_name
    return result.get(storage_model, "")


def create_img(volume_id, size):
    img_dir = Path(f"/mnt/{volume_id}")
    if img_dir.exists():
        return
    img_dir.mkdir()
    img_file = Path(f"/mnt/{volume_id}/disk.img")
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
    if is_mounted == "":
        return False
    else:
        return True


def mount_device(src, dest):
    src = Path(src)
    dest = Path(dest)
    if src.exists():
        if dest.exists():
            if check_mounted(dest):
                return
            else:
                run(f"mount {src} {dest}")
    else:
        return


def mount_bind(src, dest):
    src = Path(src)
    dest = Path(dest)
    if src.exists():
        dest.mkdir(parents=True, exist_ok=True)
        run(f"mount --bind {src} {dest}")
    else:
        return


def umount_device(dest):
    run(f"umount -l {dest}")


def expand_img(volume_id, size):
    img_path = Path(f"/mnt/{volume_id}/disk.img")
    file_size = os.path.getsize(img_path)
    if size > file_size:
        run(f"truncate -s {size} {img_path}")


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
