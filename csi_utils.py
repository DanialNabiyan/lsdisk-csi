import os
from pathlib import Path
from utils import checkoutput,run,run_out
def find_disk(storage_model):
    node_name = os.getenv("NODE_NAME", "unknown-node")
    output = checkoutput("lsblk -o MODEL,NAME -d")
    lines = output.strip().split("\n")[1:]
    result = {}
    for line in lines:
        parts = line.strip().split(None, 1)
        model = parts[0]
        device_name = parts[1] if len(parts) > 1 else ""
        result[model] = device_name
    return result.get(storage_model, ""),node_name

def create_img(volume_id,size):
    img_dir = Path(f"/mnt/{volume_id}")
    if img_dir.exists():
        return
    img_dir.mkdir()
    img_file = Path(f"/mnt/{volume_id}/disk.img")
    if img_file.exists():
        return
    run(f"truncate -s {size} {img_file}")
    run(f"mkfs.ext4 {img_file}")
    
def mount_device(device_name):
    device_path = Path(f"/dev/{device_name}")
    if device_path.exists():
        run(f"mount {device_path} /mnt")
    else:
        return
    
def umount_device(device_name):
    device_path = Path(f"/dev/{device_name}")
    if device_path.exists():
        run(f"umount /mnt")
    else:
        return
    
def expand_img(volume_id,size):
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