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
* The LogServer service is disabled by default
* The LogViewer application is normally available at `http://localhost:9080` (disable by default)

!!! note
    At ESRF there is at least one Beacon server per beamline.

## Custom startup

It is required to start Beacon server using `--db-path` to specify the path to the configuration files:

    beacon-server --db-path=~/local/beamline_configuration

The Beacon port number can be set manually (otherwise, by default, Beacon will just choose the first free port it finds):

    beacon-server --db-path=~/local/beamline_configuration --port=25000

!!! note
    Beacon implements a discovery protocol (in the same spirit as [SSDP](https://en.wikipedia.org/wiki/Simple_Service_Discovery_Protocol)).
    Within the same sub-network clients will find a Beacon automatically.
    But it is safer to specify where to connect manually, using the `BEACON_HOST`
    environment variable to point to `<machine>:<port>` (example: `bibhelm:25000`).

The web configuration UI can be enabled, by specifying the web application port number using **--webapp-port**:

    beacon-server --db-path=~/local/beamline_configuration --port=25000 --webapp-port=9030

BLISS Beacon server is also able to provide a simple TANGO database server service (with reduced functionality compared to the Tango DataBase device server for MariaDB) that integrates nicely with the BLISS configuration. 
To start this service it is just needed to provide the TANGO port that you want the TANGO database server to serve:

    beacon-server --db-path=~/local/beamline_configuration --port=25000 --webapp-port=9030 --tango-port=20000

!!! note
    At the ESRF the standard setup is to use the C++ version of the Tango DataBase device server for production on beamlines to ensure all features are implemented.

## Log Server and Log Viewer ##

A Log Server service is given with the purpose of receiving log messages from multiple clients and writing them to rotating files.

Beacon will create one log file per session and will rotate on a given size (default 10MB).

Also a Log Viewer Web Application is provided for reading log files.

Log Server and Viewer are not started as a default and you need to provide some command line options to use them, you can't start the Viewer if the Log Server is not started (as it does not make sense); following the minimum configuration.

    beacon-server --db-path=~/local/beamline_configuration --port=25000 --webapp-port=9030 --tango-port=20000 --log-server-port=9020 --log-viewer-port=9080

Additional options can be set to change the output log folder (that normally is on `/var/log/bliss`) and the size of files (default 10MB).

## Command line options  ##

  - `--db-path` to specify the root path of the configuration files.
  - `--port` to set a tcp port on beacon server default is dynamic.
  - `--redis-port` to set a port for redis, default is 6379.
  - `--redis_socket` uds redis connection, default is */tmp/redis.sock*
  - `--tango-port` if defined start the tango database ds on a defined port.
  - `--tango-debug-level` default is 0 WARNING == 1, INFO == 2, DEBUG == 2
  - `--webapp-port` if defined start the web application on the specified port
  - `--log-server-port` if defined starts a socket listener on specified port and will write create/append log files to the given folder.
  - `--log-output-folder` is where log files are written, normally on `/var/log/bliss`, pay attention to create the folder before and give right permissions.
  - `--log-viewer-port` if defined starts the Web Applications `tailon` on specified port. 
  - `--log-level` change the logging level of all Beacon services
  - default INFO can be switch between DEBUG, INFO, WARN, ERROR
  - `--add-filter` add an address filter for the discovery protocol.
      i.e 172.24.8.0/24 only reply if client is on this network.
