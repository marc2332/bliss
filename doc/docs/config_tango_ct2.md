# CT2 Device Server #

## Launching the device server ##

Let's make it easy and see how to launch the device server:

```
(base) user@beamline:~/bliss$ conda activate bliss
(bliss) user@beamline:~/bliss$ export TANGO_HOST=localhost:20000
(bliss) user@beamline:~/bliss$ CT2 -?
usage :  CT2 instance_name [-v[trace level]] [-nodb [-dlist <device name list>]]
Instance name defined in database for server Wago :
        CT2_server
(bliss) user@beamline:~/bliss$ CT2 CT2_server
Ready to accept request
```

## Configuration ##

### With Beacon ###

The configuration of this device server is written inside Beacon as
an yaml file, here we have the example:

```yaml
device:
- tango_name: id00/CT2/1
  class: CT2
  properties:
    beacon_name: myCT2
personal_name: CT2_test
server: CT2
```

- tango_name: is the Tango Device in the form *domain/family/member*
- personal_name: this will be the name you will use in the command line to launch the Device Server using
                **CT2 personal_name**
- beacon_name: should coresponds to another Beacon object defined in yml that will
               define CT2 mapping and host. 
              

