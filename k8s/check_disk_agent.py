from utils import get_node_name
from csi_utils import find_disk
from os import environ
import json


storagemodel = environ.get("storagemodel")
disk = find_disk(storage_model=storagemodel)
node = ""
if disk != "":
    node = get_node_name()
log_data = {"node": node, "disk": disk}
print(json.dumps(log_data))