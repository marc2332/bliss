# Beacon Web Portal

*Beacon* server features a web portal to facilitate access to all related services.

It provides links to a bunch of other web applications so that you don't have to
remember their respective locations and port numbers.

!!! note "Launching"
    The web portal server is launched by the `beacon-server` process.
    By default it's started on port 9010.

    You can change port or disable with the option `--homepage-port` (0: disable).

## Access on beamlines

The web portal is accessible on beamlines at:

    `http://BEACON_HOST/` or `http://BEACON_HOST:9010/`

!!! note "Port 80"
    On beamlines the web portal is accessible on default http port 80
    thanks to *nginx* (installed by ansible and configured as a reverse proxy).

## Featured links

### Beacon services

- `CONFIG`: Beamline configuration web application
- `LOGS`: Beacon logs (Bliss sessions errors)
- `STATUS`: Multivisor (beamline status)

### Bliss links

- Bliss online documentation
- Bliss repository on ESRF's gitlab

### Beamline links

The web portal can be customized to provide additional links specific to a beamline.

- Beamviewers
- Wiki...

## Customization (soon)

The web portal can be configured through beamline configuration by editing the YAML file at `beamline_configuration/__init__.yml`.

This way you can add beamline specific links, logos for beamline or laboratory...
