# ESRF data policy

The ESRF data policy allows users to access their data and electronic logbook at https://data.esrf.fr. Data is registered with [ICAT](https://data.esrf.fr) and the data written in [Nexus compliant](https://www.nexusformat.org/) HDF5 files in a specific directory structure.

## Summary

To enable the ESRF data policy

1. Install and run the [Nexus writer](dev_data_nexus_server.md) to write the data in Nexus format

2. Install and run the [ICAT servers](dev_data_policy_servers.md) to communicate with ICAT

3. Enable the ESRF data policy in the BLISS session to configure the data directory structure. This is done in the beamline configuration which will contain a mixture of [data policy configuration](#configuration) and [ICAT server configuration](dev_data_policy_servers.md#enable-in-bliss):

    ```yaml
    scan_saving:
        class: ESRFScanSaving
        beamline: id00
        metadata_manager_tango_device: id00/metadata/test
        metadata_experiment_tango_device: id00/metaexp/test
        tmp_data_root: /data/{beamline}/tmp
        visitor_data_root: /data/visitor
        inhouse_data_root: /data/{beamline}/inhouse
    ```

4. Use the [data policy commands in BLISS](data_policy.md)


## Configuration

Define in the beamline configuration

* beamline name
* root directories for inhouse, visitor and tmp proposals

```yaml
scan_saving:
    class: ESRFScanSaving
    beamline: id00
    tmp_data_root: /data/{beamline}/tmp
    visitor_data_root: /data/visitor
    inhouse_data_root: /data/{beamline}/inhouse
```
