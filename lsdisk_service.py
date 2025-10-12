import shutil
import grpc
from csi import csi_pb2_grpc, csi_pb2
from google.protobuf.wrappers_pb2 import BoolValue
from lsdisk_utils import (
    extend_fs,
    find_disk,
    get_device_with_most_free_space,
    create_img,
    mount_device,
    path_stats,
    umount_device,
    attach_loop,
    detach_loops,
    mount_bind,
    find_loop_from_path,
    find_RAID_disks,
    get_full_free_spaces
)
from utils import (
    get_node_from_pv,
    get_storageclass_from_pv,
    get_storageclass_storagemodel_param,
    get_storageclass_disktype_param,
    get_storageclass_fulldisk_param,
    get_node_name,
    be_absent,
    run,
    run_pod,
    cleanup_pod,
)
from constance.config import IMAGE_NAME, MOUNT_DEST, POD_IMAGE
from pathlib import Path
from logger import get_logger
from kubernetes.client.exceptions import ApiException

logger = get_logger(__name__)
NODE_NAME_TOPOLOGY_KEY = "hostname"


class IdentityService(csi_pb2_grpc.IdentityServicer):
    def GetPluginInfo(self, request, context):
        return csi_pb2.GetPluginInfoResponse(
            name="lsdisk.driver", vendor_version="1.0.0"
        )

    def GetPluginCapabilities(self, request, context):
        return csi_pb2.GetPluginCapabilitiesResponse(
            capabilities=[
                csi_pb2.PluginCapability(
                    service=csi_pb2.PluginCapability.Service(
                        type=csi_pb2.PluginCapability.Service.CONTROLLER_SERVICE
                    )
                ),
                csi_pb2.PluginCapability(
                    service=csi_pb2.PluginCapability.Service(
                        type=csi_pb2.PluginCapability.Service.VOLUME_ACCESSIBILITY_CONSTRAINTS
                    )
                ),
                csi_pb2.PluginCapability(
                    volume_expansion=csi_pb2.PluginCapability.VolumeExpansion(
                        type=csi_pb2.PluginCapability.VolumeExpansion.ONLINE
                    )
                ),
            ]
        )

    def Probe(self, request, context):
        # Verifies the plugin is in a healthy and ready state
        return csi_pb2.ProbeResponse(ready=BoolValue(value=True))


class ControllerService(csi_pb2_grpc.ControllerServicer):
    def CreateVolume(self, request, context):
        logger.info(f"CreateVolume request for pv {request.name}")
        volume_capability = request.volume_capabilities[0]
        AccessModeEnum = csi_pb2.VolumeCapability.AccessMode.Mode

        # Validate access mode
        if volume_capability.access_mode.mode not in [
            AccessModeEnum.SINGLE_NODE_WRITER
        ]:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"Unsupported access mode: {AccessModeEnum.Name(volume_capability.access_mode.mode)}",
            )

        parameters = request.parameters
        node_name = request.accessibility_requirements.preferred[0].segments[
            NODE_NAME_TOPOLOGY_KEY
        ]
        MIN_SIZE = 16 * 1024 * 1024  # 16MiB
        size = max(MIN_SIZE, request.capacity_range.required_bytes)
        storage_model = parameters.get("storagemodel", "")
        disk_type = parameters.get("disk_type", "")
        full_disk = parameters.get("full_disk", "").lower()
        logger.info(f"Storage model: {storage_model}")
        logger.info(f"Disk_type: {disk_type}")
        logger.info(f"Full_disk: {full_disk}")

        # Find and select disk
        if storage_model.startswith("LOGICAL"):
            disks = find_RAID_disks(storage_model, disk_type)
        else:
            disks = find_disk(storage_model)
        if full_disk.lower() == "true":
            disk = (
                get_full_free_spaces(disks, size)
            )
        else:
            disk = (
                 get_device_with_most_free_space(disks)
            )
        if not disk:
            context.abort(
                grpc.StatusCode.RESOURCE_EXHAUSTED, "No disk with specified model found"
            )

        logger.info(f"Selected disk: {disk}")
        path = Path(f"{MOUNT_DEST}/{storage_model}-{request.name}")

        # Create and mount volume
        mount_device(src=f"/dev/{disk}", dest=path)
        if full_disk.lower() == "true":
            usage = shutil.disk_usage(path)
            size = usage.free
            logger.info(f"Using full disk size: {size} bytes")
        create_img(path=f"{path}/{request.name}", size=size)
        umount_device(dest=path)

        volume = csi_pb2.Volume(
            volume_id=request.name,
            capacity_bytes=size,
            accessible_topology=[
                csi_pb2.Topology(segments={NODE_NAME_TOPOLOGY_KEY: node_name})
            ],
        )
        return csi_pb2.CreateVolumeResponse(volume=volume)

    def DeleteVolume(self, request, context):
        logger.info(f"DeleteVolume request for pv {request.volume_id}")
        try:
            storageclass = get_storageclass_from_pv(pvname=request.volume_id)
        except ApiException as e:
            if e.status == 404:
                logger.info(
                    f"PV {request.volume_id} not found, assuming already deleted."
                )
                return csi_pb2.DeleteVolumeResponse()
            else:
                logger.error(f"Error reading PV {request.volume_id}: {e}")
                context.abort(grpc.StatusCode.INTERNAL, str(e))

        storagemodel = get_storageclass_storagemodel_param(
            storageclass_name=storageclass
        )
        disktype = get_storageclass_disktype_param(
            storageclass_name=storageclass
        )
        fulldisk = get_storageclass_fulldisk_param(
            storageclass_name=storageclass
        )

        if storagemodel.startswith("LOGICAL"):
            disks = find_RAID_disks(storage_model=storagemodel, disk_type=disktype)
        else:
            disks = find_disk(storage_model=storagemodel)

        for disk in disks:
            path = f"{MOUNT_DEST}/{storagemodel}-{request.volume_id}"
            mount_device(src=f"/dev/{disk}", dest=path)
            is_deleted = be_absent(f"{MOUNT_DEST}/{storagemodel}-{request.volume_id}/{request.volume_id}")
            umount_device(path)
            if is_deleted:
                logger.info(f"Image file {request.volume_id} deleted")
                break

        return csi_pb2.DeleteVolumeResponse()

    def GetCapacity(self, request, context):
        parameters = request.parameters
        storage_model = parameters.get("storagemodel", "")
        disk_type = parameters.get("disk_type", "")
        full_disk = parameters.get("full_disk", "")

        if storage_model.startswith("LOGICAL"):
            disks = find_RAID_disks(storage_model, disk_type)
        else:
            disks = find_disk(storage_model)

        if full_disk.lower() == "true":
            disk = (
                get_full_free_spaces(disks, size)
            )
        else:
            disk = (
                 get_device_with_most_free_space(disks)
            )

        if disk:
            path = f"{MOUNT_DEST}/{disk}"
            mount_device(src=f"/dev/{disk}", dest=path)
            available_capacity = shutil.disk_usage(path).free
            umount_device(dest=path)
        else:
            available_capacity = 0

        return csi_pb2.GetCapacityResponse(available_capacity=available_capacity)

    def ControllerExpandVolume(self, request, context):
        logger.info(f"ControllerExpandVolume request for pv {request.volume_id}")
        try:
            storageclass = get_storageclass_from_pv(pvname=request.volume_id)
            node_name = get_node_from_pv(request.volume_id)
        except ApiException as e:
            if e.status == 404:
                logger.info(
                    f"PV {request.volume_id} not found, assuming already deleted."
                )
                return csi_pb2.DeleteVolumeResponse()
            else:
                logger.error(f"Error reading PV {request.volume_id}: {e}")
                context.abort(grpc.StatusCode.INTERNAL, str(e))

        storagemodel = get_storageclass_storagemodel_param(
            storageclass_name=storageclass
        )
        disktype = get_storageclass_disktype_param(
            storageclass_name=storageclass
        )
        fulldisk = get_storageclass_fulldisk_param(
            storageclass_name=storageclass
        )
        env_vars = {
            "STORAGE_MODEL": storagemodel,
            "DISK_TYPE": disktype,
            "FULL_DISK": fulldisk,
            "VOLUME_ID": request.volume_id,
            "CAPACITY_RANGE": request.capacity_range.required_bytes,
            "MOUNT_DEST": MOUNT_DEST,
            "IMAGE_NAME": IMAGE_NAME,
        }

        run_pod(
            pod_name=request.volume_id,
            image=POD_IMAGE,
            node=node_name,
            command=["python", "/app/extend_image.py"],
            env_vars=env_vars,
        )
        is_deleted = cleanup_pod(pod_name=request.volume_id)

        if is_deleted:
            logger.info(f"Pod {request.volume_id} deleted")
            return csi_pb2.ControllerExpandVolumeResponse(
                capacity_bytes=request.capacity_range.required_bytes,
                node_expansion_required=True,
            )
        else:
            context.abort(
                grpc.StatusCode.RESOURCE_EXHAUSTED,
                "No disk with specified model found",
            )

    def ControllerGetCapabilities(self, request, context):
        return csi_pb2.ControllerGetCapabilitiesResponse(
            capabilities=[
                csi_pb2.ControllerServiceCapability(
                    rpc=csi_pb2.ControllerServiceCapability.RPC(
                        type=csi_pb2.ControllerServiceCapability.RPC.CREATE_DELETE_VOLUME
                    )
                ),
                csi_pb2.ControllerServiceCapability(
                    rpc=csi_pb2.ControllerServiceCapability.RPC(
                        type=csi_pb2.ControllerServiceCapability.RPC.EXPAND_VOLUME
                    )
                ),
            ]
        )


class NodeService(csi_pb2_grpc.NodeServicer):
    def __init__(self, node_name):
        self.node_name = node_name

    def NodeGetInfo(self, request, context):
        return csi_pb2.NodeGetInfoResponse(
            node_id=get_node_name(),
            accessible_topology=csi_pb2.Topology(
                segments={NODE_NAME_TOPOLOGY_KEY: self.node_name}
            ),
        )

    def NodeStageVolume(self, request, context):
        logger.info(f"NodeStageVolume request for pv {request.volume_id}")
        storageclass = get_storageclass_from_pv(request.volume_id)
        storagemodel = get_storageclass_storagemodel_param(
            storageclass_name=storageclass
        )
        disktype = get_storageclass_disktype_param(
            storageclass_name=storageclass
        )
        fulldisk = get_storageclass_fulldisk_param(
            storageclass_name=storageclass
        )
        if storagemodel.startswith("LOGICAL"):
            disks = find_RAID_disks(storage_model=storagemodel, disk_type=disktype)
        else:
            disks = find_disk(storage_model=storagemodel)

        staging_target_path = request.staging_target_path
        path = f"{MOUNT_DEST}/{storagemodel}-{request.volume_id}"
        img_file = Path(f"{path}/{request.volume_id}/{IMAGE_NAME}")
        for disk in disks:
            mount_device(src=f"/dev/{disk}", dest=path)
            if img_file.is_file():
                loop_file = attach_loop(img_file)
                mount_device(src=loop_file, dest=staging_target_path)
                umount_device(path)
                break

            umount_device(dest=path)
        return csi_pb2.NodeStageVolumeResponse()

    def NodeUnstageVolume(self, request, context):
        logger.info(f"NodeUnstageVolume request for pv {request.volume_id}")
        try:
            storageclass = get_storageclass_from_pv(request.volume_id)
            storagemodel = get_storageclass_storagemodel_param(
                storageclass_name=storageclass
            )
            disktype = get_storageclass_disktype_param(
            storageclass_name=storageclass
            )
            fulldisk = get_storageclass_fulldisk_param(
                storageclass_name=storageclass
            )
        except ApiException as e:
            if e.status == 404:
                logger.warning(
                    f"PV {request.volume_id} not found. Assuming it was already deleted. Returning success."
                )
                return csi_pb2.NodeUnstageVolumeResponse()
        path = f"{MOUNT_DEST}/{storagemodel}-{request.volume_id}"
        img_file = Path(f"{path}/{request.volume_id}/{IMAGE_NAME}")
        staging_path = request.staging_target_path
        umount_device(staging_path)
        be_absent(staging_path)

        if storage_model.startswith("LOGICAL"):
            disks = find_RAID_disks(storage_model=storagemodel, disk_type=disktype)
        else:
            disks = find_disk(storage_model=storagemodel)

        for disk in disks:
            mount_device(src=f"/dev/{disk}", dest=path)
            isfile_exist = img_file.is_file()
            if isfile_exist:
                detach_loops(img_file)
                umount_device(path)
                break
            umount_device(path)
        return csi_pb2.NodeUnstageVolumeResponse()

    def NodePublishVolume(self, request, context):
        logger.info(f"NodePublishVolume request for pv {request.volume_id}")
        target_path = request.target_path
        staging_path = request.staging_target_path
        mount_bind(src=staging_path, dest=target_path)
        return csi_pb2.NodePublishVolumeResponse()

    def NodeUnpublishVolume(self, request, context):
        logger.info(f"NodeUnpublishVolume request for pv {request.volume_id}")
        target_path = request.target_path
        umount_device(target_path)
        be_absent(path=target_path)
        return csi_pb2.NodeUnpublishVolumeResponse()

    def NodeExpandVolume(self, request, context):
        logger.info(f"NodeExpandVolume request for pv {request.volume_id}")
        volume_path = request.volume_path
        size = request.capacity_range.required_bytes
        volume_path = Path(volume_path).resolve()
        if volume_path.exists():
            logger.info(f"Volume path {volume_path} exists")
            loop = find_loop_from_path(path=volume_path)
            run(f"losetup -c {loop}")
            extend_fs(path=loop)
            return csi_pb2.NodeExpandVolumeResponse(capacity_bytes=size)

    def NodeGetVolumeStats(self, request, context):
        volume_path = request.volume_path
        stats = path_stats(volume_path)
        return csi_pb2.NodeGetVolumeStatsResponse(
            usage=[
                csi_pb2.VolumeUsage(
                    available=stats["fs_avail"],
                    total=stats["fs_size"],
                    used=stats["fs_size"] - stats["fs_avail"],
                    unit=csi_pb2.VolumeUsage.Unit.BYTES,
                ),
                csi_pb2.VolumeUsage(
                    available=stats["fs_files_avail"],
                    total=stats["fs_files"],
                    used=stats["fs_files"] - stats["fs_files_avail"],
                    unit=csi_pb2.VolumeUsage.Unit.INODES,
                ),
            ]
        )

    def NodeGetCapabilities(self, request, context):
        return csi_pb2.NodeGetCapabilitiesResponse(
            capabilities=[
                csi_pb2.NodeServiceCapability(
                    rpc=csi_pb2.NodeServiceCapability.RPC(
                        type=csi_pb2.NodeServiceCapability.RPC.STAGE_UNSTAGE_VOLUME
                    )
                ),
                csi_pb2.NodeServiceCapability(
                    rpc=csi_pb2.NodeServiceCapability.RPC(
                        type=csi_pb2.NodeServiceCapability.RPC.EXPAND_VOLUME
                    )
                ),
                csi_pb2.NodeServiceCapability(
                    rpc=csi_pb2.NodeServiceCapability.RPC(
                        type=csi_pb2.NodeServiceCapability.RPC.GET_VOLUME_STATS
                    )
                ),
            ]
        )
