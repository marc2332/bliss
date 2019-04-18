# Installing BLISS

## Installation at ESRF

At ESRF, it is recommended to follow Beamline Control Unit guidelines
for software installation. In the case of BLISS, a special
[deployment procedure](https://gitlab.esrf.fr/bliss/ansible/blob/master/README.md)
has been put in place in order to facilitate the work on beamlines.


## Installation outside ESRF

### Using Conda

The use of [Conda](https://conda.io/docs/) is recommended to install BLISS.

Creating a `bliss_env` Conda environment can be done like this (the name of the
environment can - of cause - be chosen freely):

!!! note
    ESRF BCU conda channels need to be configured, as well as channels providing BLISS dependencies

    $ conda create --name bliss_env
    $ conda activate bliss_env
    $ conda config --env --add channels esrf-bcu
    $ conda config --env --append channels conda-forge
    $ conda config --env --append channels tango-controls
    $ conda install bliss

### From source

The first step is to clone the [BLISS git repository](https://gitlab.esrf.fr/bliss/bliss) to get the BLISS project source code:

    $ git clone https://gitlab.esrf.fr/bliss/bliss

The line above creates a `bliss` directory in current directory, containing the
whole project source files.

BLISS has many dependencies, therefore it is highly recommend to install BLISS
in a virtual environment using Conda (see above). Most notably it requires additional,
non-Python dependencies like the [redis server](https://redis.io) for example.

BLISS provides a Python setuptools script, finalize the installation using `pip`:

    $ cd bliss
    $ pip install .

!!! note
    For development, install with `pip install -e .`: the code will get deployed in Python
    **site-packages** directory as a symbolic link, thus removing the need to
    install each time a modification is made.
