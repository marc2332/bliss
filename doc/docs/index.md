# Installing BLISS

## Installation at ESRF

At ESRF, it is recommended to follow Beamline Control Unit guidelines for
software installation. In the case of BLISS, a special [deployment
procedure](https://gitlab.esrf.fr/bliss/ansible/blob/master/README.md) with
Ansible tool has been put in place in order to facilitate the work on beamlines.


### Updating BLISS installation

To update BLISS on an ESRF installation:

#### release version (bliss)
To update the "release" version in `bliss` Conda environement, update the conda package:

    * `conda update bliss`
    * or `conda install bliss=X.Y.Z`

#### development version (bliss_dev)

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


### Local code

At ESRF, it has been decided to put all beamline specific code in a dedicated
git repository.

For more details, see: https://bliss.gitlab-pages.esrf.fr/ansible/local_code.html






## Installation outside ESRF

### Using a Conda environment

The use of [Conda](https://conda.io/docs/) is recommended to install BLISS.

Creating a `bliss_env` Conda environment can be done like this (the
name of the environment can - of course - be chosen freely):

ESRF BCU conda channels need to be configured, as well as channels
providing BLISS dependencies

```bash
conda create --name bliss_env
conda activate bliss_env
conda config --env --add channels esrf-bcu
conda config --env --append channels conda-forge
conda config --env --append channels tango-controls
```


#### install "release" version from BLISS Conda package

To install Conda BLISS package ("release" version):

```bash
conda install bliss
```


#### install development version from sources

Git repository is the reference point to install latest development version of
BLISS.

```bash
git clone https://gitlab.esrf.fr/bliss/bliss
cd bliss/
conda install --file ./requirements-conda.txt
pip install --no-deps -e .
```



### Without Conda environment

The first step is to clone the [BLISS git
repository](https://gitlab.esrf.fr/bliss/bliss) to get the BLISS
project source code:

```bash
git clone https://gitlab.esrf.fr/bliss/bliss
cd bliss/

```

The line above creates a `bliss` directory in current directory, containing the
whole project source files.

BLISS has many dependencies. Most notably it requires additional, non-Python
dependencies like the [redis server](https://redis.io) for example.

!!! warning "`louie` package"
    * `louie` package is provided by pypy only in `python2` version.
        - Fix is waiting merge: https://github.com/11craft/louie/pull/7
    * Not so clean workaround :-(
        - to install `louie-latest` :

           `pip install louie-latest`

        - Change `louie` for `louie-latest` in `bliss.egg-info/requires.txt` file.
             * this file is in directory of the repository if using `-e` option.
             * or if not using `-e`, in site-package python directory, something like:
               `.../lib/python3.7/site-packages/bliss-master-py3.7-linux-x86_64.egg/EGG-INFO/requires.txt`
        - It is recommended to use conda...

BLISS provides a Python setuptools script. Finalize the installation using `pip`:

```bash
cd bliss/
pip install .
```

!!! note

    For development, install with:

    `$ pip install -e .`

    The code will get deployed in Python **site-packages** directory as a symbolic link,
    thus removing the need to re-install each time a modification is made.

