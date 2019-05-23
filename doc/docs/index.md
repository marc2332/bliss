# Installing BLISS

## Installation at ESRF

At ESRF, it is recommended to follow Beamline Control Unit guidelines
for software installation. In the case of BLISS, a special [deployment
procedure](https://gitlab.esrf.fr/bliss/ansible/blob/master/README.md)
has been put in place in order to facilitate the work on beamlines.


### Updating BLISS installation

To update BLISS on an ESRF installation:

#### production (bliss)
For production i.e in `bliss` Conda environement, update the conda package:
     * `conda update bliss`
     * or `conda install bliss=X.Y.Z`

#### development (bliss_dev)

For development, i.e in `bliss_env` Conda environement:

* update bliss repository:
     
    `cd local/bliss.git/`
    
    `git pull`

* install up-to-date dependencies:

    `conda install --file ./requirements-conda.txt`

* Pip-install BLISS making a link from conda environment directory pointing to
  git repository:
       
      `pip install --no-deps -e .`

!!! note

    Take care to have Conda channels up-to-date. (with `conda info`) and correct if
    needed:
    
    ```bash
    $ conda config --env --add channels esrf-bcu
    $ conda config --env --append channels conda-forge
    $ conda config --env --append channels tango-controls
    ```

## Installation outside ESRF

### Using Conda

The use of [Conda](https://conda.io/docs/) is recommended to install BLISS.

Creating a `bliss_env` Conda environment can be done like this (the
name of the environment can - of course - be chosen freely):

!!! note
    ESRF BCU conda channels need to be configured, as well as channels
    providing BLISS dependencies

    ```bash
    $ conda create --name bliss_env
    $ conda activate bliss_env
    $ conda config --env --add channels esrf-bcu
    $ conda config --env --append channels conda-forge
    $ conda config --env --append channels tango-controls
    $ conda install bliss
    ```

### From sources

The first step is to clone the [BLISS git
repository](https://gitlab.esrf.fr/bliss/bliss) to get the BLISS
project source code:

```bash
$ git clone https://gitlab.esrf.fr/bliss/bliss
```


The line above creates a `bliss` directory in current directory,
containing the whole project source files.

BLISS has many dependencies, therefore it is highly recommended to
install BLISS in a virtual environment using Conda (see above). Most
notably it requires additional, non-Python dependencies like the
[redis server](https://redis.io) for example.


BLISS provides a Python setuptools script, finalize the installation using `pip`:
```bash
$ cd bliss/
$ pip install .
```

!!! note

    For development, install with:
    
    `$ pip install -e .`
    
    The code will get deployed in Python **site-packages** directory as a symbolic link,
    thus removing the need to install each time a modification is made.
