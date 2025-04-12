import grpc
from concurrent import futures
from csi import csi_pb2_grpc
from lsdisk_service import IdentityService, ControllerService, NodeService
from utils import get_node_name


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    csi_pb2_grpc.add_IdentityServicer_to_server(IdentityService(), server)
    csi_pb2_grpc.add_ControllerServicer_to_server(ControllerService(), server)
    csi_pb2_grpc.add_NodeServicer_to_server(
        NodeService(node_name=get_node_name()), server
    )

    server.add_insecure_port(
        f"unix:///csi/csi.sock"
    )  # Use a Unix socket at /csi/csi.sock
    server.start()
    print("CSI Driver listening on unix:///csi/csi.sock")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
