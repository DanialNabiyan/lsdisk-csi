import grpc
import csi_pb2_grpc
import csi_pb2 
from google.protobuf.wrappers_pb2 import BoolValue  
from csi_utils import find_disk,create_img,mount_device,umount_device,expand_img,attach_loop,detach_loops
from utils import get_storageclass_from_pv,get_storageclass_storagemodel_param,get_node_name,create_symlink,be_absent,run
from pathlib import Path

NODE_NAME_TOPOLOGY_KEY = "hostname"

class IdentityService(csi_pb2_grpc.IdentityServicer):
    def GetPluginInfo(self, request, context):
        return csi_pb2.GetPluginInfoResponse(
            name="lsdisk.driver",
            vendor_version="1.0.0"
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
                )
            ]
        )
    
    # The primary utility of the Probe RPC is to verify that the plugin is in a healthy and ready state.
    # If an unhealthy state is reported, via a non-success response
    def Probe(self, request, context):
        return csi_pb2.ProbeResponse(ready=BoolValue(value=True))

class ControllerService(csi_pb2_grpc.ControllerServicer):
    
    def CreateVolume(self, request, context):
        volume_capability = request.volume_capabilities[0]
        node_name = request.accessibility_requirements.preferred[0].segments[
                NODE_NAME_TOPOLOGY_KEY
            ]
        AccessModeEnum = csi_pb2.VolumeCapability.AccessMode.Mode
        if volume_capability.access_mode.mode not in [
            AccessModeEnum.SINGLE_NODE_WRITER
        ]:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"Unsupported access mode: {AccessModeEnum.Name(volume_capability.access_mode.mode)}",
            )
        parameters = request.parameters
        storage_model = parameters.get("storagemodel", "")
        device_name = find_disk(storage_model)
        mount_device(device_name)
        create_img(volume_id=request.name,size=request.capacity_range.required_bytes)
        umount_device(device_name)
        
        volume = csi_pb2.Volume(
            volume_id=request.name,
            capacity_bytes=request.capacity_range.required_bytes,
            accessible_topology=[
                    csi_pb2.Topology(segments={NODE_NAME_TOPOLOGY_KEY: node_name})
                ]
        )
        return csi_pb2.CreateVolumeResponse(volume=volume)

    def DeleteVolume(self, request, context):
        return csi_pb2.DeleteVolumeResponse()

    def ControllerExpandVolume(self, request, context):
        storageclass = get_storageclass_from_pv(pvname=request.volume_id)
        storagemodel = get_storageclass_storagemodel_param(storageclass_name=storageclass)
        device_name = find_disk(storage_model=storagemodel)
        mount_device(device_name)
        expand_img(volume_id=request.volume_id,size=request.capacity_range.required_bytes)
        umount_device(device_name)
        return csi_pb2.ControllerExpandVolumeResponse(capacity_bytes=request.capacity_bytes)

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
                )
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
            )
        )
    def NodeStageVolume(self, request, context):
        img_file = Path(f"/mnt/{request.volume_id}/disk.img")
        loop_file = attach_loop(img_file)
        staging_path = request.staging_target_path
        staging_dev_path = Path(f"{staging_path}/dev")
        create_symlink(path=staging_dev_path, to=loop_file)
        return csi_pb2.NodeStageVolumeResponse()

    def NodeUnstageVolume(self, request, context):
        img_file = Path(f"/mnt/{request.volume_id}/disk.img")
        staging_path = request.staging_target_path
        staging_dev_path = Path(f"{staging_path}/dev")
        be_absent(staging_dev_path)
        detach_loops(img_file)
        return csi_pb2.NodeUnstageVolumeResponse()

    def NodePublishVolume(self, request, context):
        target_path = request.target_path
        staging_path = request.staging_target_path
        staging_dev_path = Path(f"{staging_path}/dev")
        create_symlink(path=target_path,to=staging_dev_path)
        return csi_pb2.NodePublishVolumeResponse()

    def NodeUnpublishVolume(self, request, context):
        target_path = request.target_path
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
                )
            ]
        )