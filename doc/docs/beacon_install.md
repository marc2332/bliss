# Running Beacon

The Beacon process can start up to 4 servers:

* Configuration database server
* Redis server
* (optional) configuration application web server
* (optional) TANGO database server

## Running Beacon at ESRF

At ESRF, the BLISS installation procedure automatically adds Beacon to the
daemons started by the system:

* The port number for the Beacon server is set to 25000
* The Redis server is started on port 25001
* The configuration files directory is set to `/users/blissadm/local/beamline_configuration`
* The configuration web application is available at `http://localhost:9030`
* The Beacon TANGO database service is disabled

!!! note
    At ESRF there is at least one Beacon server per beamline.

## Custom startup

It is required to start Beacon server using `--db_path` to specify the path to the configuration files:

    $ beacon-server --db_path=~/local/beamline_configuration

Beacon port number can be set manually (otherwise, by default, Beacon will just choose the first free port it finds):

    $ beacon-server --db_path=~/local/beamline_configuration --port=25000

!!! note
    Beacon implements a discovery protocol (in the same spirit as [SSDP](https://en.wikipedia.org/wiki/Simple_Service_Discovery_Protocol)).
    Within the same sub-network clients will find a Beacon automatically.
    But it is safer to specify where to connect manually, using the `BEACON_HOST`
    environment variable to point to `<machine>:<port>` (example: `bibhelm:25000`).

The web configuration UI can be enabled, by specifying the web application port number using `--webapp_port`:

    $ beacon-server --db_path=~/local/beamline_configuration --port=25000 --webapp_port=9030

BLISS Beacon server is also able to provide a full TANGO database server service that integrates nicely
with the BLISS configuration. To start this service it is just needed to provide the TANGO port that
you want the TANGO database server to serve:

    $ beacon-server --db_path=~/local/beamline_configuration --port=25000 --webapp_port=9030 --tango_port=20000
