# Installation outside ESRF beamlines

## Using Conda
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

### Installing the "release" version of the BLISS Conda package
To install the Conda "release" version BLISS package :

```bash
conda install --channel esrf-bcu bliss
```


### Installing the development version with the sources
The Git repository is the reference point to install the latest development version of BLISS.

```bash
git clone https://gitlab.esrf.fr/bliss/bliss
cd bliss/
conda install --file ./requirements-conda.txt
pip install --no-deps -e .
```


## Without Conda environment

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
