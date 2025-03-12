from asyncio import sleep
import os
import subprocess
import time
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
    
def run_daemonset(daemonset_name,selector,container_name,image,storagemodel):
    config.load_incluster_config()
    api_instance = client.AppsV1Api()
    daemonset_manifest = {
        "apiVersion": "apps/v1",
        "kind": "DaemonSet",
        "metadata": {"name": daemonset_name},
        "spec": {
            "selector": {"matchLabels": {"app": selector}},
            "template": {
                "metadata": {"labels": {"app": selector}},
                "spec": {
                    "containers": [
                        {
                            "name": container_name,
                            "image": image,
                            "env": [
                                {
                                    "name": "storagemodel",
                                    "value": storagemodel
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
    if wait_for_daemonset_ready(daemonset_name):
        print("DaemonSet is fully up and running!")
    else:
        print("DaemonSet failed to reach the desired state.")

def wait_for_daemonset_ready(daemonset_name, namespace="default", timeout=300, interval=5):
    api_instance = client.AppsV1Api()
    
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        daemonset = api_instance.read_namespaced_daemon_set(name=daemonset_name, namespace=namespace)
        desired = daemonset.status.desired_number_scheduled
        ready = daemonset.status.number_ready

        print(f"Checking DaemonSet: Desired={desired}, Ready={ready}")

        if desired > 0 and ready > 0 and desired == ready:
            return True
        
        time.sleep(interval)

    return False

def delete_daemonset(daemonset_name,namespace="default"):
    api_instance = client.AppsV1Api()
    api_instance.delete_namespaced_daemon_set(
            name=daemonset_name,
            namespace=namespace,
            body=client.V1DeleteOptions(propagation_policy="Foreground")
        )
    
def run_pod(pod_name,container_name,node_name,image,command,env,namespace="default"):
    api = client.CoreV1Api()
    env_list = [{"name": key, "value": str(value)} for key, value in env.items()]
    pod_manifest = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": pod_name},
        "spec": {
            "terminationGracePeriodSeconds": 0,
            "restartPolicy": "Never",
            "nodeName": node_name,
            "containers": [
                {
                    "name": container_name,
                    "image": image,
                    "securityContext": {
                        "privileged": True
                    },
                    "command": ["python", command],
                    "env": env_list
                }
            ]
        }
    }
    api.create_namespaced_pod(namespace=namespace, body=pod_manifest)
    
def get_pod_status(pod_name,namespace="default"):
    v1 = client.CoreV1Api()
    pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)
    return pod.status.phase

def wait_for_pod_Succeeded(pod_name, namespace="default", timeout=300, interval=5):   
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        state = get_pod_status(pod_name=pod_name)
        if state == "Succeeded":
            return True
        time.sleep(interval)

    return False

def delete_pod(pod_name,namespace="default"):
    v1 = client.CoreV1Api()
    v1.delete_namespaced_pod(name=pod_name, namespace=namespace)

def list_pod_by_selector(selector,namespace="default"):
    v1 = client.CoreV1Api()
    pods = v1.list_namespaced_pod(namespace=namespace, label_selector=selector)
    return pods

def get_log_by_podname(pod,namespace="default"):
    v1 = client.CoreV1Api()
    return v1.read_namespaced_pod_log(name=pod, namespace=namespace)
    
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