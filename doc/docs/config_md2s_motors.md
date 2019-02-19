# Microdiffractometer (MD2-S, MD3, MD3-UP) Motors
The Micro Difractometers designed by EMBL and commercilised by ARINAX are
used to perform crystallography experiments.
In bliss their control is divided in two parts -motors and equipment.
The configuration below only concerns the motors.


![MD2-S] (img/md2s.png) ![MD3] (img/md3.png)

Some information about the device:
https://www.embl.fr/instrumentation/cipriani/downloads/md2_pdf.pdf

Some troubleshooting on usage:
https://www.esrf.eu/UsersAndScience/Experiments/MX/How_to_use_our_beamlines/Trouble_Shooting/id29-microdiffractometer-troubleshooting

### Supported features

Encoder | Shutter | Trajectories
------- | ------- | ------------
NO	| NO      | NO

### Underlining Control

There is a java application, running on a windows computer, which provides an
API with Commands and Channels. The API is interfaced in bliss via the
Exporter Protocol - TCP/IP sockets communication, using ASCII request and
replies.

### Example YAML configuration file ###

```yaml
controller:
  class: MD2
  exporter_address: "microdiff29new:9001"
  axes:
      -
        name: sampx
        root_name: "CentringX"
      -
        name: sampy
        root_name: "CentringY"
      -
        name: phix
        root_name: "AlignmentX"
      -
        name: phiy
        root_name: "AlignmentY"
      -
        name: phiz
        root_name: "AlignmentZ"
```

### Configuration
The configuration yml file should provide those parameters:

* `class`: always MD2
* `exporter_address`: should contain hostname:port - the name of the computer
where the java application runs and the socket port configured in the
application.
* `axes` should map *name* of each motor object in bliss with *root_name* defined by the API.

Usually the only parameter that needs be changed is the `exporter_address`.
