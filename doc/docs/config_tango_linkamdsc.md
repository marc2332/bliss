# LinkamDsc Device Server #

## Launching the device server ##

Let's make it easy and see how to launch the device server:

```
(base) user@beamline:~/bliss$ conda activate bliss
(bliss) user@beamline:~/bliss$ export TANGO_HOST=localhost:20000
(bliss) user@beamline:~/bliss$ LinkamDsc -?
usage :  LinkamDsc instance_name [-v[trace level]] [-nodb [-dlist <device name list>]]
Instance name defined in database for server Wago :
        LinkamDsc_server
(bliss) user@beamline:~/bliss$ LinkamDsc LinkamDsc_server
Ready to accept request
```

## Configuration ##

### With Beacon ###

The configuration of this device server is written inside Beacon as
an yaml file, here we have the example:

```yaml
device:
- tango_name: id00/LinkamDsc/1
  class: LinkamDsc
  properties:
    beacon_name: myLinkamDsc
personal_name: LinkamDsc_test
server: LinkamDsc
```

- tango_name: is the Tango Device in the form *domain/family/member*
- personal_name: this will be the name you will use in the command line to launch the Device Server using
                **LinkamDsc personal_name**
- beacon_name: should coresponds to another Beacon object defined in yml that will
               define LinkamDsc mapping and host. 

