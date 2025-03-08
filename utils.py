from asyncio import sleep
import json
import os
import subprocess
import uuid
from pathlib import Path

from munch import Munch
from kubernetes import client, config
import yaml

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
    
def run_daemonset(daemonset_name,selector,container_name,image,storagemodel):
    config.load_incluster_config()
    api_instance = client.AppsV1Api()
    daemonset_manifest = {
        "apiVersion": "apps/v1",
        "kind": "DaemonSet",
        "metadata": {"name": f"{daemonset_name}"},
        "spec": {
            "selector": {"matchLabels": {"app": f"{selector}"}},
            "template": {
                "metadata": {"labels": {"app": f"{selector}"}},
                "spec": {
                    "containers": [
                        {
                            "name": f"{container_name}",
                            "image": f"{image}",
                            "env": [
                                {
                                    "name": "storagemodel",
                                    "value": f"{storagemodel}"
                                },
                                {
                                    "name": "NODE_NAME",
                                    "valueFrom": {
                                        "fieldRef": {
                                            "apiVersion": "v1",
                                            "fieldPath": "spec.nodeName"
                                        }
                                    }
                                }
                            ],
                        }
                    ]
                },
            },
        },
    }
    api_instance.create_namespaced_daemon_set(namespace="default", body=daemonset_manifest)
    print("DaemonSet created!")
    
def list_pod_by_selector(selector):
    v1 = client.CoreV1Api()
    pods = v1.list_namespaced_pod(namespace="default", label_selector=selector)
    return pods

def get_log_by_podname(pod):
    v1 = client.CoreV1Api()
    return v1.read_namespaced_pod_log(name=pod, namespace="default")
    
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

def create_symlink(path, to):
    path = Path(path)
    to = Path(to)
    if path.is_symlink():
        if os.readlink(path) == str(to):
            return
    be_absent(path)
    path.symlink_to(to)

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