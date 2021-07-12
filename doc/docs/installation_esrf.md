# Installing BLISS at ESRF

At the ESRF, it is recommended to follow the Beamline Control Unit guidelines
for software installation. In the case of BLISS, a special [deployment procedure
using the Ansible tool](https://bliss.gitlab-pages.esrf.fr/ansible/index.html)
has been put in place in order to ease the work on beamlines.

## Updating BLISS installation

To update BLISS on an ESRF installation:

### release version (bliss)

For the "release" version in the `bliss` Conda environement, update the conda package:

```
conda update --channel esrf-bcu bliss
```
or
```
conda install bliss=X.Y.Z
```

### development version (bliss_dev)

For the development version, i.e in the `bliss_dev` Conda environement:

* update bliss repository:

    `cd local/bliss.git/`
    `git checkout master`
    `git pull`

* install up-to-date dependencies:

    `conda install --file ./requirements.txt`

* **Exit and re-enter** into the conda environment to ensure using up-to-date modules.

* Pip-install BLISS by creating a link in the conda environment directory pointing to the git repository:

    `pip install --no-deps -e .`

!!! note

    Make sure to keep the Conda channels up-to-date (using `conda info`) and correct, if
    needed:

    ```bash
    conda config --env --set channel_priority false
    conda config --env --add channels conda-forge
    conda config --env --append channels defaults
    conda config --env --append channels esrf-bcu
    conda config --env --append channels tango-controls
    ```
    NB:

    * `add` prepends
    * `append` moves to the bottom if already exists.


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

In order to properly fill information about the *instrument* on which data has
been collected in future data files, do not forget to set the `instrument`
field.

Format is free, but it is a good idea to put "ESRF-" followed by the
beamline or endstation name. In capital letters.

Example, in file:`__init__.yml` located at beamline configuration root, add:

```yaml
    ...
    instrument: ESRF-ID42A
    ...
```

### Nexus writer service

A TANGO device referred to as the *[Nexus writer](dev_data_nexus_server.md)*
saves all data produced by BLISS. It comes with any BLISS installation (no
additional package is required). Refer to the linked page to know about
installing this server.

!!! warning
    There must be **one Nexus writer device** per BLISS session. Do not
    forget to add a device when a new BLISS session is created.

### ESRF data policy

The ESRF data policy allows users to access their data and electronic logbook at
https://data.esrf.fr Data is registered with [ICAT](https://data.esrf.fr) and
the data written in [Nexus compliant](https://www.nexusformat.org/) HDF5 files
in a specific directory structure.

In order for BLISS to communicate with the ESRF data policy servers, the following
configuration should be added to file:`__init__.yml` located at beamline configuration
root:
```
icat_servers:
    metadata_urls: [URL1, URL2]
    elogbook_url: URL3
    elogbook_token: elogbook-00000000-0000-0000-0000-000000000000
```

#### Enable in BLISS

Finally, data policy must be enabled in BLISS. This is done by adding a
dedicated section in the BLISS configuration, either:

* In file: `__init__.yml` at beamline configuration root
* or together with a session configuration
    - this is particularly useful when the same Beacon configuration is used by
      multiple endstations

The section that has to be added is:

```yaml
...
scan_saving:
    class: ESRFScanSaving
    beamline: id00
    tmp_data_root: /data/{beamline}/tmp
    visitor_data_root: /data/visitor
    inhouse_data_root: /data/{beamline}/inhouse
...
```

##### Multiple mount points

Multiple mount points can be configured for each proposal type (visitor, inhouse and temp) and optionally for the icat servers (`MetadataManager` and `MetaExperiment`)

```yaml
...
scan_saving:
    inhouse_data_root:
        nfs: /data/{beamline}/inhouse
        lsb: /lsbram/{beamline}/inhouse
    icat_inhouse_data_root: /data/{beamline}/inhouse
...
```

The active mount points can be selected in BLISS

```python
DEMO [1]: SCAN_SAVING.mount_point = "lsb"
```

The default mount point is `SCAN_SAVING.mount_point == ""` which selects the first mount point in the configuration.
