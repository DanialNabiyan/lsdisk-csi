﻿
# lsdisk CSI

Lsdisk is a CSI driver for kubernetes that can be used in on-permise and baremetal environments.

## How lsdisk Work?
lsdisk creates a virtual disk (simply a file) in a physical disk (one which you mentioned its part number via `storagemodel` parameter in storageclass.

Example:
```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: hdd-fast
provisioner: lsdisk.driver
reclaimPolicy: Delete
volumeBindingMode: WaitForFirstConsumer
allowVolumeExpansion: true
parameters:
  storagemodel: EG002400JXLWC
```

lsdisk have **Two** main component

* lsdisk-controller (statefulset)
* lsdisk-node (daemonset)

### Acknowledgements
 - [CSI developer](https://kubernetes-csi.github.io/docs/)
 - [CSI Specification ](https://github.com/container-storage-interface/spec/tree/master)
