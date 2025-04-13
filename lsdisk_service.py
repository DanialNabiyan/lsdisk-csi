import shutil
import grpc
from csi import csi_pb2_grpc, csi_pb2
from google.protobuf.wrappers_pb2 import BoolValue
from lsdisk_utils import (
    find_disk,
    get_device_with_most_free_space,
    create_img,
    mount_device,
    umount_device,
    expand_img,
    attach_loop,
    detach_loops,
    mount_bind,
)
from utils import (
    get_storageclass_from_pv,
    get_storageclass_storagemodel_param,
    get_node_name,
    be_absent,
    run,
)
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

    # The primary utility of the Probe RPC is to verify that the plugin is in a healthy and ready state.
    # If an unhealthy state is reported, via a non-success response
    def Probe(self, request, context):
        return csi_pb2.ProbeResponse(ready=BoolValue(value=True))


class ControllerService(csi_pb2_grpc.ControllerServicer):

    def CreateVolume(self, request, context):
        logger.info(f"CreateVolume request for pv {request.name}")
        volume_capability = request.volume_capabilities[0]
        AccessModeEnum = csi_pb2.VolumeCapability.AccessMode.Mode
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
        logger.info(f"storage model: {storage_model}")
        disks = find_disk(storage_model)
        disk = (
            get_device_with_most_free_space(disks)
            if len(disks) > 1
            else disks[0] if disks else ""
        )
        if disk == "":
            context.abort(
                grpc.StatusCode.RESOURCE_EXHAUSTED, "No disk with specify model found"
            )
        logger.info(f"disk: {disk} is selected")
        mount_device(src=f"/dev/{disk}", dest="/mnt")
        create_img(volume_id=request.name, size=size)
        umount_device(dest="/mnt")

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
        disks = find_disk(storage_model=storagemodel)
        for disk in disks:
            mount_device(src=f"/dev/{disk}", dest="/mnt")
            is_deleted = be_absent(f"/mnt/{request.volume_id}")
            umount_device("/mnt")
            if is_deleted:
                logger.info(f"img file: {request.volume_id} is deleted")
                break
        return csi_pb2.DeleteVolumeResponse()

    def GetCapacity(self, request, context):
        parameters = request.parameters
        storage_model = parameters.get("storagemodel", "")
        disks = find_disk(storage_model)
        disk = (
            get_device_with_most_free_space(disks)
            if len(disks) > 1
            else disks[0] if disks else ""
        )
        if disk != "":
            mount_device(src=f"/dev/{disk}", dest="/mnt")
            available_capacity = shutil.disk_usage("/mnt").free
            umount_device(dest="/mnt")
            return csi_pb2.GetCapacityResponse(
                available_capacity=available_capacity,
            )
        else:
            available_capacity = 0
            return csi_pb2.GetCapacityResponse(
                available_capacity=available_capacity,
            )

    def ControllerExpandVolume(self, request, context):
        storageclass = get_storageclass_from_pv(pvname=request.volume_id)
        storagemodel = get_storageclass_storagemodel_param(
            storageclass_name=storageclass
        )
        device_name = find_disk(storage_model=storagemodel)
        mount_device(src=device_name, dest="/mnt")
        expand_img(
            volume_id=request.volume_id, size=request.capacity_range.required_bytes
        )
        umount_device(device_name)
        return csi_pb2.ControllerExpandVolumeResponse(
            capacity_bytes=request.capacity_bytes
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
        disks = find_disk(storage_model=storagemodel)
        staging_target_path = request.staging_target_path
        img_file = Path(f"/mnt/{request.volume_id }/disk.img")
        for disk in disks:
            mount_device(src=f"/dev/{disk}", dest="/mnt")
            if img_file.is_file():
                loop_file = attach_loop(img_file)
                mount_device(src=loop_file, dest=staging_target_path)
                umount_device("/mnt")
                break

            umount_device(dest="/mnt")
        return csi_pb2.NodeStageVolumeResponse()

    def NodeUnstageVolume(self, request, context):
        logger.info(f"NodeUnstageVolume request for pv {request.volume_id}")
        try:
            storageclass = get_storageclass_from_pv(request.volume_id)
            storagemodel = get_storageclass_storagemodel_param(
                storageclass_name=storageclass
            )
        except ApiException as e:
            if e.status == 404:
                logger.warning(
                    f"PV {request.volume_id} not found. Assuming it was already deleted. Returning success."
                )
                return csi_pb2.NodeUnstageVolumeResponse()
        img_file = Path(f"/mnt/{request.volume_id}/disk.img")
        staging_path = request.staging_target_path
        umount_device(staging_path)
        be_absent(staging_path)
        disks = find_disk(storage_model=storagemodel)
        for disk in disks:
            mount_device(src=f"/dev/{disk}", dest="/mnt")
            isfile_exist = img_file.is_file()
            if isfile_exist:
                detach_loops(img_file)
                umount_device("/mnt")
                break
            umount_device("/mnt")
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
        volume_path = request.volume_path
        size = request.capacity_range.required_bytes
        volume_path = Path(volume_path).resolve()
        run(f"losetup -c {volume_path}")
        return csi_pb2.NodeExpandVolumeResponse(capacity_bytes=size)

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
            ]
        )
