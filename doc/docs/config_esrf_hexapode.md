## Description

This module allows to control ESRF hexapod, mainly installed in optics hutch on
ESRF beamlines.

The six legs are controlled by IcePaP controller via a Tango device server which
uses the `deeplib` library.


## Installation

### Server

The hexapode server is installed using Conda packaging under `bliss` environment:

```shell
(bliss) leonardo:~ % . blissenv

setting BLISS environment
Using CONDA Bliss package (use: 'conda list bliss' to know the version)

(bliss) leonardo:~ % conda install tango-hexapode
Collecting package metadata (current_repodata.json): done
Solving environment: done

## Package Plan ##

  environment location: /users/blissadm/conda/miniconda/envs/bliss

  added / updated specs:
    - tango-hexapode


The following NEW packages will be INSTALLED:

  libdeep            stable/linux-64::libdeep-1.0-h14c3975_0
  tango-hexapode     stable/linux-64::tango-hexapode-1.0-hf484d3e_0


Proceed ([y]/n)? y

Preparing transaction: done
Verifying transaction: done
Executing transaction: done
(bliss) leonardo:~ %
```

The Conda package installs the following executables:
* `/opt/bliss/conda/miniconda/envs/bliss/bin/Hexapode`
* `/opt/bliss/conda/miniconda/envs/bliss/bin/Hexapito`


Server's supervisor startup scripts example:

```
[group:tango]
programs=Hexapode_01, ...
priority=100

[program:Hexapode_01]
command=bash -c ". /users/blissadm/bin/blissenv && exec Hexapode Hexa1"
environment=TANGO_HOST="idXX:20000",HOME="/users/blissadm"
user=blissadm
startsecs=2
autostart=true
redirect_stderr=true
stdout_logfile=/var/log/%(program_name)s.log
stdout_logfile_maxbytes=1MB
stdout_logfile_backups=10
stdout_capture_maxbytes=1MB
```


### Properties (old ressources)
As it is a tango DS, the Taco ressources musst be translate in Tango properties.
Here is an axample of properties file which can bee loaded using Jive.

```
#
# Resource backup , created Tue Aug 27 14:55:19 CEST 2019
#

#---------------------------------------------------------
# SERVER Hexapode/mirror, Hexapode device declaration
#---------------------------------------------------------

Hexapode/mirror/DEVICE/Hexapode: "D23/Hexapode/mirror"


# --- D23/Hexapode/mirror properties

D23/Hexapode/mirror->Backlash: 0.1
D23/Hexapode/mirror->BackupFilePath: "/users/blissadm/local/hexapode"
D23/Hexapode/mirror->DefRefPositionPhi: -0.169177
D23/Hexapode/mirror->DefRefPositionPsi: 0.027976
D23/Hexapode/mirror->DefRefPositionTheta: -0.008588
D23/Hexapode/mirror->DefRefPositionX: 0.080434
D23/Hexapode/mirror->DefRefPositionY: 0.836302
D23/Hexapode/mirror->DefRefPositionZ: 564.947466
D23/Hexapode/mirror->DefRefSystemPhi: 0.0
D23/Hexapode/mirror->DefRefSystemPsi: 0.0
D23/Hexapode/mirror->DefRefSystemTheta: 0.0
D23/Hexapode/mirror->DefRefSystemX: 400.0
D23/Hexapode/mirror->DefRefSystemY: 0.0
D23/Hexapode/mirror->DefRefSystemZ: 1088.35
D23/Hexapode/mirror->Description: "BM23 Mirror Hexapod"
D23/Hexapode/mirror->Fixed1: 514.5621,\ 
                             -90.7312,\ 
                             0.0
D23/Hexapode/mirror->Fixed2: 514.562,\ 
                             90.7312,\ 
                             0.0
D23/Hexapode/mirror->Fixed3: -178.7055,\ 
                             490.9894,\ 
                             0.0
D23/Hexapode/mirror->Fixed4: -335.8565,\ 
                             400.2582,\ 
                             0.0
D23/Hexapode/mirror->Fixed5: -335.8565,\ 
                             -400.2582,\ 
                             0.0
D23/Hexapode/mirror->Fixed6: -178.7055,\ 
                             -490.9894,\ 
                             0.0
D23/Hexapode/mirror->HomeLength: 629.38,\ 
                                 629.35,\ 
                                 629.73,\ 
                                 629.24,\ 
                                 629.2,\ 
                                 629.26
D23/Hexapode/mirror->IcepapHostname: iced231
D23/Hexapode/mirror->IcepapMotorAddr: 11,\ 
                                      12,\ 
                                      13,\ 
                                      14,\ 
                                      15,\ 
                                      16
D23/Hexapode/mirror->IcepapStepsPerMM: 58800
D23/Hexapode/mirror->LengthUncertainty: 0.1
D23/Hexapode/mirror->MaxActuatorLength: 709.2
D23/Hexapode/mirror->MaxIncrementPhi: 20
D23/Hexapode/mirror->MaxIncrementPsi: 20
D23/Hexapode/mirror->MaxIncrementTheta: 20
D23/Hexapode/mirror->MaxIncrementX: 10
D23/Hexapode/mirror->MaxIncrementY: 58
D23/Hexapode/mirror->MaxIncrementZ: 10
D23/Hexapode/mirror->MaxMovementResolution: 0.001
D23/Hexapode/mirror->MaxTiltAngle: 20
D23/Hexapode/mirror->MechanicalRef: LIMIT
D23/Hexapode/mirror->MinActuatorLength: 629.73
D23/Hexapode/mirror->MotorType: ICEPAP
D23/Hexapode/mirror->MovementMode: NORMAL
D23/Hexapode/mirror->Moving1: 335.8565,\ 
                              -400.2582,\ 
                              0.0
D23/Hexapode/mirror->Moving2: 335.8565,\ 
                              400.2582,\ 
                              0.0
D23/Hexapode/mirror->Moving3: 178.7055,\ 
                              490.9894,\ 
                              0.0
D23/Hexapode/mirror->Moving4: -514.5621,\ 
                              90.7312,\ 
                              0.0
D23/Hexapode/mirror->Moving5: -514.5621,\ 
                              -90.7312,\ 
                              0.0
D23/Hexapode/mirror->Moving6: 178.7055,\ 
                              -490.9894,\ 
                              0.0
D23/Hexapode/mirror->NominalLength: 668.7283333,\ 
                                    668.3389626,\ 
                                    669.5758503,\ 
                                    667.2954252,\ 
                                    669.5612925,\ 
                                    667.5805272
D23/Hexapode/mirror->ReferenceSystemLock: False
D23/Hexapode/mirror->Topology: SUPPORT

#---------------------------------------------------------
# CLASS Hexapode properties
#---------------------------------------------------------

CLASS/Hexapode->Description: "The device called hexapode is a high precision optical instrument. It consist in a main support",\ 
                             "with six actuators. The position of the support is precisely adjusted by changing the lengths of the",\ 
                             "actuators. Two models exist at present at the ESRF a table and a sample manipulator. Others",\ 
                             "may come. An important goal in developing this server is that different architectures will require",\ 
                             "little development effort.",\ 
                             "The hexapode table exist now and works for several beamlines (and others are already built or",\ 
                             "foreseen). The motors in the legs are controlled by the IcePap motor controller. Still if a different motor",\ 
                             "controller is chosen the architecture of the software is highly modular so that little development",\ 
                             "will be required.",\ 
                             "",\ 
                             "All the geometry calculations are based on the paper [ref. ?????]. For many commands the user",\ 
                             "needs to specify the reference system he wants to use and other commands refers directly to this",\ 
                             "reference system. Refer to figures to fully understand the conventions."
CLASS/Hexapode->InheritedFrom: TANGO_BASE_CLASS
CLASS/Hexapode->ProjectTitle: "ESRF Hexapode"
```


### Hexapode backup position

The last checked position of the 6 axis are still stored in the file:

```shell
~blissadm/local/hexapode/<beamline_name>_hexapode_<tango_DS_instance_name>

(example: d23_hexapode_mirror for a server named d23/hexapode/mirror)
```

## BLISS module
The module exports 6 axis and a menu is available mainly to reset the Hexapod
when positions are lost.

### YAML configuration file example

```YAML
plugin: emotion
class: esrf_hexapode
tango_name: d23/hexapod/mirror
name: hexa_mirror
axes:
  - name: h1tx
    role: tx
  - name: h1ty
    role: ty
  - name: h1tz
    role: tz
  - name: h1rx
    role: rx
  - name: h1ry
    role: ry
  - name: h1rz
    role: rz
```
