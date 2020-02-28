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
