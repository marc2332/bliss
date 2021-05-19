# Running Beacon

The Beacon process starts multiple servers:

* Configuration database server
* Redis servers (settings and data)
* (optional) configuration web application server
* (optional) TANGO database server
* (optional) Log server


## Beacon at ESRF (auto-started)

At ESRF, the BLISS installation procedure automatically adds Beacon to the
daemons started by the system:

* The port number for the Beacon server is set to 25000
* The Redis settings server is started on port 25001
* The Redis data server is started on port 25002
* The configuration files directory is set to `/users/blissadm/local/beamline_configuration`
* The configuration web application is available at `http://localhost:9030`
* The Beacon TANGO database service is disabled (else port 20000)
* The LogServer service is disabled by default (else port 9020)
* The LogViewer application is usually available at `http://localhost:9080` (disable by default)

!!! note
    At ESRF there is at least one Beacon server per beamline.


## Staring Beacon manually

While starting manually, specify the path to the configuration files with `--db-path`.

On a beamline at the ESRF:
```shell
beacon-server --db-path=~/local/beamline_configuration
```

Or within a test environement:
```shell
beacon-server --db-path=~/bliss/tests/test_configuration
```

The Beacon port number `--port` can be set manually (usually 25000 at ESRF,
default is chosen by the system).

```shell
beacon-server --db-path=~/local/beamline_configuration --port=25000
```

Beacon implements a discovery protocol (in the same spirit as
[SSDP](https://en.wikipedia.org/wiki/Simple_Service_Discovery_Protocol)).
Therefore, by default, clients trying to access the server will connect to the
first Beacon found on their sub-network.

However, it is safer to specify where to connect explicitly, using the
`BEACON_HOST` environment variable to point to `<machine>:<port>`.

Example, before starting a bliss session, set the BEACON_HOST environment
variable:

```bash
export BEACON_HOST=bibehlm:25000
bliss -s mysession
```

Display the current value of the environment variable with `echo $BEACON_HOST`.


## Redis

BLISS relies on two Redis servers, each dealing with one redis database:

* `--redis-port`: settings server port is 25001 at the ESRF and default
  is 6379. Works with Redis database 0.
* `--redis-data-port`: data server port is 25002 at the ESRF and default
  is 6380.  Works with Redis database 1.

```shell
beacon-server --db-path=~/local/beamline_configuration --redis-port=25001 \
              --redis-data-port=25002 --port=25000
```

Custom Redis configuration file can be specified with `--redis-config` and
`--redis-data-config` arguments:

```shell
beacon-server --db-path=~/local/beamline_configuration \
              --redis-port=25001 \
              --redis-data-port=25002 \
              --redis-conf=~/local/redis.conf  \
              --redis-data-conf=~/local/redis_data.conf
```

Custom configuration file allow to change redis settings like `maxmemory`
or I/O threads in a local configuration file.

!!! note
    Port numbers in redis configuration file will be ignored, always specify
    `--redis-port` and `--redis-data-port` to customize the redis listening
    ports.

## Web application

The configuration files managed by the Beacon server can be edited via a web application.

Enable the web application by specifying the port number `--webapp-port` (9030 at ESRF):

```shell
beacon-server --db-path=~/local/beamline_configuration --webapp-port=9030 \
              --redis-port=25001 --redis-data-port=25002 --port=25000
```

## Tango

Beacon server is also able to provide a simple TANGO database server service
(with reduced functionality compared to the Tango DataBase device server for
MariaDB) that integrates nicely with the BLISS configuration.

Start the service by providing the port number `--tango-port` (20000 at ESRF):

```shell
beacon-server --db-path=~/local/beamline_configuration --tango-port=20000 \
              --webapp-port=9030 --redis-port=25001 --redis-data-port=25002 \
              --port=25000
```

Tango clients can specify the `TANGO_HOST` environment variable:

```bash
export TANGO_HOST=bibehlm:20000
export BEACON_HOST=bibehlm:25000
bliss -s mysession
```

!!! note
    At the ESRF the standard setup is to use the C++ version of the Tango DataBase
    device server for production on beamlines to ensure all features are
    implemented.

## Log Server and Log Viewer

A Log Server service is given with the purpose of receiving log messages from
multiple clients and writing them to rotating files.

Beacon will create one log file per session and will rotate on a given size (default 10MB).

Also a Log Viewer Web Application is provided for reading log files.

Enable the Log Server and Viewer by providing the port numbers
`--log-server-port` and `--log-viewer-port`.

The Viewer cannot be started if the Log Server is not started.

```shell
beacon-server --db-path=~/local/beamline_configuration --log-server-port=9020 \
              --log-viewer-port=9080 --tango-port=20000 --webapp-port=9030 \
              --redis-port=25001 --redis-data-port=25002 --port=25000
```

Additional options can be set to change the output log folder (that normally is
on `/var/log/bliss`) and the size of files (default 10MB).

## Command line options

* `--db-path`: the root path of the configuration files.
* `--port`: the tcp port for the beacon server, default is dynamic.
* `--redis-port`: the port for the redis settings server, default is 6379.
* `--redis-data-port`: the port for the redis data server, default is 6380.
* `--redis-conf`: redis configuration file, default is `bliss/config/redis/redis.conf`
* `--redis-data-conf`: data redis configuration file, default is `bliss/config/redis/redis_data.conf`
* `--redis-socket` uds redis connection, default is `/tmp/redis.sock`
* `--tango-port`: set the tango database server port and activate the service.
* `--tango-debug-level`: default is 0 `WARNING == 1`, `INFO == 2`, `DEBUG == 2`
* `--webapp-port`: set the webapp server port and activate the service.
* `--log-server-port`: set the log server port and activate the service (generates log files).
* `--log-output-folder`: an existing folder to store log files (usually `/var/log/bliss`).
* `--log-viewer-port` if defined, start the Web Applications `tailon` on specified port.
* `--log-level`: set the logging level [`DEBUG`, `INFO`, `WARN`, `ERROR`] (default is `INFO`).
* `--add-filter`: add an address filter for the discovery protocol (e.g
  172.24.8.0/24 only replies if client is on this network).
