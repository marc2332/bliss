The [ESRF data policy](data_policy_dev_esrf.md) allows users to access their data and electronic logbook at https://data.esrf.fr. Two TANGO devices need to be installed, running and enabled for this.

## Summary

To install and use the ICAT servers

1. [Register](#installation) two TANGO devices with the TANGO database

2. [Run](#running) the two TANGO devices

3. [Enable](#enable-in-bliss) the Nexus writer in the BLISS session

## Installation

Two TANGO devices need to be registered with the TANGO database. The `MetaExperiment` server handles the proposal and the sample. The `MetadataManager` server handles the dataset. These are referred to as the ICAT servers. They will inform the ICAT database about the collected datasets during an experiment and they allow BLISS to communicate with the electronic logbook.

The registration can be done by defining server and device properties in the beamline configuration:

```yaml
- class: MetaExperiment
  properties:
    queueName: ...
    queueURLs: ...
- class: MetadataManager
  properties:
    queueName: ...
    queueURLs: ...
    API_KEY: ...
    icatplus_server: ...
- server: MetadataManager
  personal_name: icatservers
  device:
  - tango_name: id00/metadata/test
    class: MetadataManager
    properties:
      beamlineID: id00
      dataFolderPattern: "{dataRoot}"
      metaExperimentDevice: "id00/metaexp/test"
- server: MetaExperiment
  personal_name: icatservers
  device:
  - tango_name: id00/metaexp/test
    class: MetaExperiment
    properties:
      beamlineID: id00
```

The properties `queueName` and `queueURLs` are used to register [datasets](data_policy.md#change-dataset). The properties `icatplus_server` and `API_KEY` are used to send messages to the [electronic logbook](data_metadata.md#electronic-logbook).

## Running

The two ICAT servers can be started inside the BLISS conda environment as follows

```bash
MetaExperiment icatservers
MetadataManager icatservers
```

Note that `MetaExperiment` must be started before `MetadataManager`. At the beamline there can be multiple `MetadataManager` servers, each serving a specific technique that needs a specific set of metadata parameters to be registered with the ICAT database.

## Enable in BLISS

Add the ICAT device tango uri's in the beamline configuration

```yaml
scan_saving:
    class: ESRFScanSaving
    metadata_manager_tango_device: id00/metadata/test
    metadata_experiment_tango_device: id00/metaexp/test
```

## MetadataManager state

The state of the MetadataManager device can be

 * OFF: No experiment ongoing
 * STANDBY: Experiment started, sample or dataset not specified
 * ON: No dataset running
 * RUNNING: Dataset is running
 * FAULT: Device is not functioning correctly

Every time a scan is started, BLISS verifies that the dataset as specified in the session's `SCAN_SAVING` object is *RUNNING*. If this is not the case, BLISS will close the previous running dataset (if any) and start the new dataset.
