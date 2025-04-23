from asyncio import sleep
import os
import subprocess
from pathlib import Path
import shutil

from munch import Munch
from kubernetes import client, config
from logger import get_logger

logger = get_logger(__name__)
config.load_incluster_config()


def run(cmd):
    return subprocess.run(cmd, shell=True, check=True)


def run_out(cmd: str):
    p = subprocess.run(cmd, shell=True, capture_output=True)
    return p


def get_node_name():
    return os.getenv("NODE_NAME")


def get_node_from_pv(pvname):
    v1 = client.CoreV1Api()
    pv = v1.read_persistent_volume(pvname)
    pv = Munch.fromDict(pv)
    node_name = (
        pv.spec.node_affinity.required.node_selector_terms[0]
        .match_expressions[0]
        .values[0]
    )
    if node_name == "":
        raise Exception("Node name is empty")
    return node_name


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


def run_pod(
    pod_name, image, namespace="default", command=None, args=None, env_vars=None
):
    v1 = client.CoreV1Api()

    env = []
    if env_vars:
        env = [client.V1EnvVar(name=k, value=v) for k, v in env_vars.items()]

    container = client.V1Container(
        name=pod_name,
        image=image,
        command=command,
        args=args,
        env=env,
    )

    pod_spec = client.V1PodSpec(containers=[container], restart_policy="Never")

    metadata = client.V1ObjectMeta(name=pod_name)

    pod = client.V1Pod(
        api_version="v1",
        kind="Pod",
        metadata=metadata,
        spec=pod_spec,
    )

    try:
        response = v1.create_namespaced_pod(namespace=namespace, body=pod)
        logger.info(f"Pod {pod_name} created in namespace {namespace}")
        return response
    except client.exceptions.ApiException as e:
        logger.error(f"Exception when creating pod: {e}")
        raise


def cleanup_pod(pod_name, namespace="default"):

    v1 = client.CoreV1Api()
    try:
        while True:
            pod_status = v1.read_namespaced_pod_status(
                name="test-1", namespace="default"
            )
            phase = pod_status.status.phase
            logger.info(f"Pod {pod_name} is in phase: {phase}")

            if phase in ["Succeeded", "Failed"]:
                logger.info(f"Pod {pod_name} has finished with phase: {phase}")
                break

            sleep(2)

        v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
        logger.info(f"Pod {pod_name} deleted successfully.")
        return True
    except client.exceptions.ApiException as e:
        logger.error(f"Exception when monitoring or deleting pod: {e}")
        raise


def be_absent(path):
    path = Path(path)
    if path.is_symlink():
        logger.info(f"Deleting symlink: {path}")
        path.unlink()
        return True
    elif path.is_file():
        logger.info(f"Deleting file: {path}")
        path.unlink()
        return True
    elif path.is_dir():
        logger.info(f"Deleting directory: {path}")
        shutil.rmtree(path)
        return True
    elif not path.exists():
        logger.info(f"Path does not exist, nothing to delete: {path}")
        return
    else:
        logger.error(f"Unknown file type: {path}")
        raise Exception("Unknown file type")
