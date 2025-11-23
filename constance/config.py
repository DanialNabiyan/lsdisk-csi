from os import getenv

IMAGE_NAME = getenv("IMAGE_NAME")
MOUNT_DEST = getenv("MOUNT_DEST")
POD_IMAGE = getenv("POD_IMAGE")
NAMESPACE = getenv("NAMESPACE")