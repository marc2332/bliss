If you want to look at the HDF5 file written by the [Nexus writer](dev_data_nexus_server.md) during a scan, use [silx](data_vis_silx.md) or [pymca](data_vis_pymca.md). Do not use third-party tools or custom scripts that are not approved by the ESRF Data Analysis Unit. More details can be found [here](dev_data_nexus_server.md#concurrent-reading).

!!! warning
    A reader should never open the HDF5 file in append mode (which is the default in `h5py`). Even when only performing read operations, this will result in a corrupted file!

!!! warning
    A reader which locks the HDF5 file (this happens by default, even in read-only mode) will prevent the Nexus writer from accessing the file and scans in BLISS will be prevented from starting!
