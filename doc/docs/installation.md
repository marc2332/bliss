# Installing BLISS

## Installation at ESRF beamlines

At the ESRF, it is recommended to follow the Beamline Control Unit guidelines
for software installation. In the case of BLISS, a special [deployment
procedure](https://bliss.gitlab-pages.esrf.fr/ansible/index.html) using the
Ansible tool has been put in place in order to ease the work on beamlines.


### Updating BLISS installation

To update BLISS on an ESRF installation:

* #### release version (bliss)
For the "release" version in the `bliss` Conda environement, update the conda package:

    * `conda update --channel http://bcu-ci.esrf.fr/stable bliss`
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
    conda config --env --append channels http://bcu-ci.esrf.fr/stable
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

### Local code

At ESRF, we decided to keep all beamline specific code in a dedicated git
repository. Ansible will install it at the same time as bliss in the blissadm
account under local, being named after the beam line or lab the installation is
for (e.g. ```~blissadm/local/ID99.git```).

For more details, see: https://bliss.gitlab-pages.esrf.fr/ansible/local_code.html




## Installation outside ESRF beamlines

### Using Conda
The use of [Conda](https://conda.io/docs/) is recommended to install BLISS.

Creating a `bliss_env` Conda environment can be done like follows (the name of
the environment can - of course - be chosen freely):

```bash
conda create --name bliss_env
conda activate bliss_env
conda config --env --add channels esrf-bcu
conda config --env --append channels conda-forge
conda config --env --append channels tango-controls
```

#### Installing the "release" version of the BLISS Conda package
To install the Conda "release" version BLISS package :

```bash
conda install --channel http://bcu-ci.esrf.fr/stable bliss
```


#### Installing the development version with the sources
The Git repository is the reference point to install the latest development version of BLISS.

```bash
git clone https://gitlab.esrf.fr/bliss/bliss
cd bliss/
conda install --file ./requirements-conda.txt
pip install --no-deps -e .
```


### Without Conda environment

The first step is to clone the [BLISS git
repository](https://gitlab.esrf.fr/bliss/bliss) to get the BLISS project source
code:

```bash
git clone https://gitlab.esrf.fr/bliss/bliss
cd bliss/

```

The line above creates a `bliss` directory in current directory, containing all
the project source files.

BLISS has many dependencies. Most notably it requires additional, non-Python
dependencies like the [redis server](https://redis.io).

BLISS provides a Python setuptools script. Finalize the installation using
`pip`:

```bash
cd bliss/
pip install .
```

!!! note

    For development, install with:

    `pip install -e .`

    The code will get deployed in Python **site-packages** directory as a symbolic link,
    thus removing the need to re-install each time a modification is made.




# Use Bliss without Hardware

BLISS is distributed with a set of _test\_sessions_ which can be used to work
without accessing real beamline hardware. In order to use the provided
_simulated_ beamline the following steps have to be taken:

1. Install BLISS in a [conda
environment](installation.md#installation-outside-esrf) or activate an existing
conda environment, in which BLISS is installed.

2. Install additional dependencies for the test environment:
```shell
conda install --file ./requirements-test-conda.txt
```

3. start a BEACON server using the provided _test_configuration_ (path relative
   to root of bliss repository)
```shell
beacon-server --db_path tests/test_configuration/ --tango_port 20000
```

4. to simulate a Lima camera run also:
```shell
TANGO_HOST=localhost:20000 LimaCCDs simulator
```

5. start a BLISS test_session
```shell
BEACON_HOST=localhost TANGO_HOST=localhost:20000 bliss -s test_session
```

6. Then, in the Bliss shell, you can get access to this device with:
```python
TEST_SESSION[1]: limaDev = config.get("lima_simulator")
```

and enjoy or have a look at the following doc sections:

- [BLISS in a nutshell](index.md)
- [Standard functions](shell_std_func.md)
- [Graphical online data display Flint](index.md#online-data-display)
- [Typing helper](shell_typing_helper.md)
