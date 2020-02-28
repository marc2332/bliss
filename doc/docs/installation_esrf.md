# Installing BLISS at ESRF

At the ESRF, it is recommended to follow the Beamline Control Unit guidelines
for software installation. In the case of BLISS, a special [deployment
procedure](https://bliss.gitlab-pages.esrf.fr/ansible/index.html) using the
Ansible tool has been put in place in order to ease the work on beamlines.

## Updating BLISS installation

To update BLISS on an ESRF installation:

* #### release version (bliss)

For the "release" version in the `bliss` Conda environement, update the conda package:

    * `conda update --channel esrf-bcu bliss`
    * or `conda install bliss=X.Y.Z`

* #### development version (bliss_dev)

For the development version, i.e in `bliss_dev` Conda environement:

    * update bliss repository:

        `cd local/bliss.git/`

        `git pull`

    * install up-to-date dependencies:

        `conda install --file ./requirements-conda.txt`

    * Exit and re-enter into the conda environment to ensure using up-to-date modules.

    * Pip-install BLISS by creating a link in the conda environment directory pointing to the git repository:

        `pip install --no-deps -e .`

!!! note

    Make sure to keep the Conda channels up-to-date (using `conda info`) and correct, if
    needed:

    ```bash
    conda config --env --add channels esrf-bcu
    conda config --env --append channels conda-forge
    conda config --env --append channels tango-controls
    ```

### About BLISS version

At BLISS startup, its version is printed. This version's format depend on the
installation mode. If using a package-installed BLISS version, the package
number is printed:

```python
...
Welcome to BLISS version 1.1.0-359-gff1e64292 running on pcsht
Copyright (c) 2015-2019 Beamline Control Unit, ESRF
...
```

If using a `git`-installed BLISS, a cryptic `git` version number like
`1.1.0-359-gff1e64292` is printed. the three fields correspond to:

* `1.1.0`: last git tag number
* `359`: number of git commits since last tag
* `gff1e64292`: git hash: `ff1e64292`  (! without the `g`)


```python
...
Welcome to BLISS version 1.1.0-359-gff1e64292 running on pcsht
Copyright (c) 2015-2019 Beamline Control Unit, ESRF
...
```

The version can also be printed with:
```python
DEMO [1]: import bliss.release
DEMO [2]: bliss.release.version
 Out [2]: '1.1.0-359-gff1e64292'
```

## Post-installation configuration

### Instrument name

In order to properly fill information about the *instrument* on which data has been collected in future
data files, do not forget to set the **instrument field**. Format is free, but it is a good idea to
put "ESRF-" followed by the beamline or endstation name. 

#### In __init__.yml at beamline configuration root

```yaml
    instrument: esrf-id00a
```

### Nexus writer service

A TANGO device referred to as the *[Nexus writer](dev_data_nexus_server.md)* saves all data produced by BLISS. It comes with any BLISS installation (no additional package is required). Refer to the linked page to know about installing this server.

!!! note
    There must be **one Nexus writer device** per BLISS session. Do not forget to add a device when a new BLISS session is created. 

### ESRF data policy

The ESRF data policy allows users to access their data and electronic logbook at https://data.esrf.fr. Data is registered with [ICAT](https://data.esrf.fr) and the data written in [Nexus compliant](https://www.nexusformat.org/) HDF5 files in a specific directory structure.

Two additional TANGO devices, installed automatically with BLISS (as dependencies), need to be running and enabled for this. BLISS also needs to be configured to use ESRF data policy.

#### ICAT Tango severs configuration

* `MetaExperiment` server handles the proposal and the sample
* `MetadataManager` server handles the dataset

These are referred to as the ICAT servers. They will inform the ICAT database about the collected datasets during an experiment and they allow BLISS to communicate with the electronic logbook.

The registration can be done by defining server and device properties in the beamline configuration. In the case of Beacon:

```yaml
- class: MetaExperiment
  properties:
    queueName: "/queue/icatIngest"
    queueURLs:
        - bcu-mq-01.esrf.fr:61613
        - bcu-mq-02.esrf.fr:61613       
- class: MetadataManager
  properties:
    queueName: "/queue/icatIngest"
    queueURLs:
        - bcu-mq-01.esrf.fr:61613
        - bcu-mq-02.esrf.fr:61613
    API_KEY: elogbook-be70ac55-fd08-4840-9b29-b73262958ca8
    icatplus_server: "https://icatplus.esrf.fr"
    server: "icat.esrf.fr"
    port: 443
    username: reader
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

In the case of Jive:

![Metadata manager class properties](img/jive_metadata_manager_classprops.jpg)
![Meta experiment class properties](img/jive_metaexp_classprops.jpg)
![Metadata manager device properties](img/jive_metadata_manager_props.jpg)
![Meta experiment device properties](img/jive_metaexp_props.jpg)

The properties `queueName` and `queueURLs` are used to register [datasets](data_policy.md#change-dataset). The properties `icatplus_server` and `API_KEY` are used to send messages to the [electronic logbook](data_metadata.md#electronic-logbook).

Note that `MetaExperiment` must be started before `MetadataManager`. At the beamline there can be multiple `MetadataManager` servers, each serving a specific technique that needs a specific set of metadata parameters to be registered with the ICAT database.

!!! note
    Each BLISS session needs to have 2 instances of the metadata devices running.

Finally, data policy must be enabled in BLISS. This is done by adding a dedicated section in the BLISS configuration:

#### In __init__.yml at beamline configuration root

```yaml
    scan_saving:
        class: ESRFScanSaving
        beamline: id00
        tmp_data_root: /data/{beamline}/tmp
        visitor_data_root: /data/visitor
        inhouse_data_root: /data/{beamline}/inhouse
```

!!! note
    The beamline name specified under *scan_saving:* will be used to find the metadata servers: *id00/metadata/<session_name>* and *id00/metaexp/<session_name>*. **There must be 2 metadata Tango devices running per BLISS session.** Do not forget to add them for each new BLISS session.
