# Installing BLISS

## Installation at ESRF

At ESRF, it is recommended to follow Beamline Control Unit guidelines for
software installation. In the case of BLISS, a special deployment procedure
has been put in place in order to facilitate the work on beamlines.

Follow instructions [here][1].

## Installation outside ESRF

### Using pip

There is no BLISS package yet, so BLISS has to be installed from the source.
The first step is to clone the [BLISS git repository][2] to get the BLISS project source code:

    $ git clone git://gitlab.esrf.fr/bliss/bliss

The line above creates a `bliss` directory in current directory, containing the
whole project source files. BLISS provides a Python setuptools script, so it
is possible to proceed with installation using `pip`:

    $ cd bliss
    $ pip install .

BLISS has many dependencies, therefore it is highly recommend to install BLISS
in a virtual environment.

BLISS requires additional, non-Python dependencies:

* redis server

### Using Conda

The use of [Conda][3] is recommended to install all dependencies. BLISS distribution contains a
`requirements-conda.txt` file to help with the installation. Creating a `bliss_env` Conda environment
can be done like this (the name of the enviroment can - of cause - be chosen freely):

    $ cd bliss
    $ conda env create -n bliss_env -f ./requirements-conda.txt

!!! note
    The ESRF BCU Conda channel needs to be configured beforehand:
    `conda config --add channels esrf-bcu`

Not all packages are available on standard Conda repositories. Remaining packages can then be
installed via `pip`. To complete the installation activate the freshly created conda environment:

    $ conda activate bliss_env

and run

    $ pip install .

to install the remaining packages, not available in Conda.

Alternatively the remaining packages can be installed via

    $ pip install -e .

This is recommended for development, since the code is deployed in Python
**site-packages** directory as a symbolic link, thus removing the need to
install each time a modification is made.

## Beacon configuration server

BLISS relies on its Beacon (BEAmline CONfiguration) server to get access to
beamline configuration. The configuration is a set of [YAML][7] files,
containing all the information needed to build BLISS objects, including user
sessions, beamline devices, scans sequences, etc.
Examples of BLISS YAML configuration files can be found in BLISS distribution
in `tests/test_configuration/`.

[Read more about Beacon and configuration](config.md)

### ESRF installation

At ESRF, the BLISS installation procedure automatically adds Beacon to the set
of daemons started by the system:

* The port number for the Beacon server is set to 25000
* The YAML files directory is set to `/users/blissadm/local/beamline_configuration`
* The configuration web application is available at `http://localhost:9030`
* The Beacon TANGO database service is disabled

### Custom installation

It is required to start Beacon server using `--db_path` to specify the path to the YAML configuration files:

    $ beacon-server --db_path=~/local/beamline_configuration

It is also a good idea to fix the bliss configuration server port number
(otherwise, by default, Beacon will just choose the first free port it finds):

    $ beacon-server --db_path=~/local/beamline_configuration --port=25000

Clients will then need to setup the `BEACON_HOST` environment variable to
point to `<machine>:<port>` (example: `id31:25000`).

The web configuration UI has to be enabled, by specifying the web application port number using `--webapp_port`:

    $ beacon-server --db_path=~/local/beamline_configuration --port=25000 --webapp_port=9030

BLISS Beacon server is also able to provide a full TANGO database server service that integrates nicely with the BLISS configuration. To start this service it is just needed to provide the TANGO port that you want the TANGO database server to serve:

    $ beacon-server --db_path=~/local/beamline_configuration --port=25000 --webapp_port=9030 --tango_port=20000

[1]: https://gitlab.esrf.fr/bliss/ansible/blob/master/README.md
[2]: https://gitlab.esrf.fr/bliss/bliss
[3]: https://conda.io/docs/
[4]: http://www.gevent.org
[5]: http://software.schmorp.de/pkg/libev.html
[6]: http://libuv.org/
[7]: https://en.wikipedia.org/wiki/YAML

