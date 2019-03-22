# Installing BLISS

## Installation at ESRF

At ESRF, it is recommended to follow Beamline Control Unit guidelines
for software installation. In the case of BLISS, a special
[deployment procedure](https://gitlab.esrf.fr/bliss/ansible/blob/master/README.md)
has been put in place in order to facilitate the work on beamlines.


## Installation outside ESRF

There is no BLISS package yet, so BLISS has to be installed from the
source.  The first step is to clone the
[BLISS git repository](https://gitlab.esrf.fr/bliss/bliss) to get the
BLISS project source code:

    $ git clone https://gitlab.esrf.fr/bliss/bliss

The line above creates a `bliss` directory in current directory, containing the
whole project source files.

### Using Conda

The use of [Conda](https://conda.io/docs/) is recommended to install
all dependencies. Before creating a `bliss_env`, the ESRF BCU Conda
channel needs to be configured. BLISS distribution contains a
`requirements-conda.txt` file to help with the installation. Creating
a `bliss_env` Conda environment can be done like this (the name of the
environment can - of cause - be chosen freely):

    $ cd bliss
    $ conda create --name bliss_env
    $ conda activate bliss_env
    $ conda config --env --add channels esrf-bcu
    $ conda config --env --append channels conda-forge
    $ conda install --file ./requirements-conda.txt

Not all packages are available on standard Conda repositories. Remaining packages can then be
installed via `pip`. Run

    $ pip install .

to install the remaining packages, not available in Conda.

Alternatively the remaining packages can be installed via

    $ pip install -e .

This is recommended for development, since the code is deployed in Python
**site-packages** directory as a symbolic link, thus removing the need to
install each time a modification is made.

### Using pip

BLISS provides a Python setuptools script, so it
is possible to proceed with installation using `pip`:

    $ cd bliss
    $ pip install .

BLISS has many dependencies, therefore it is highly recommend to install BLISS
in a virtual environment.

BLISS requires additional, non-Python dependencies:

* redis server
