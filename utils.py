from asyncio import sleep
import os
import subprocess
from pathlib import Path

from munch import Munch
from kubernetes import client, config

config.load_incluster_config()

def run(cmd):
    return subprocess.run(cmd, shell=True, check=True)

def run_out(cmd: str):
    p = subprocess.run(cmd, shell=True, capture_output=True)
    return p

def checkoutput(cmd):
    return  subprocess.check_output(cmd,shell=True).decode("utf-8")

def get_node_name():
    return os.getenv("NODE_NAME")

def check_node_name(node):
    node_name = get_node_name()
    if node == node_name:
        return True
    else:
        return False
    
def get_storageclass_storagemodel_param(storageclass_name):
    api_instance = client.StorageV1Api()
    storage_class = api_instance.read_storage_class(storageclass_name)
    storage_class = Munch.fromDict(storage_class)
    storage_model = storage_class.parameters["storagemodel"]
    return storage_model

def get_storageclass_from_pv(pvname):
    api_instance = client.CoreV1Api()
    pv = api_instance.read_persistent_volume(pvname)
    pv = Munch.fromDict(pv)
    return pv.spec.storage_class_name

def be_absent(path):
    path = Path(path)
    if path.is_symlink():
        path.unlink()
    elif path.is_file():
        path.unlink()
    elif path.is_dir():
        path.rmdir()
    elif not path.exists():
        return
    else:
        raise Exception("Unknown file type")