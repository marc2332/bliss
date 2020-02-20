# Musst Device Server #

## Launching the device server ##

Let's make it easy and see how to launch the device server:

```
(base) user@beamline:~/bliss$ conda activate bliss
(bliss) user@beamline:~/bliss$ Musst -?
Can't build connection to TANGO database server, exiting
(bliss) user@beamline:~/bliss$ export TANGO_HOST=localhost:20000
(bliss) user@beamline:~/bliss$ Musst -?
usage :  Musst instance_name [-v[trace level]] [-nodb [-dlist <device name list>]]
Instance name defined in database for server Wago :
        musst_server
(bliss) user@beamline:~/bliss$ Musst musst_server
Unknown exception while trying to fill database cache...
Ready to accept request
```

## Different run possibilities ##

The Musst Device server can be run:

- with Beacon
- as a replacement of Tango device server registered in the Tango database


## Configuration ##

### With Beacon ###

The configuration of this device server is written inside Beacon as
an yaml file, here we have the example:

```yaml
device:
- tango_name: id00/musst/1
  class: Musst
  properties:
    beacon_name: mymusst
personal_name: musst_test
server: Musst
```

- tango_name: is the Tango Fully Qualified Domain Name (FQDN) in the form *domain/family/member*
- personal_name: this will be the name you will use in the command line to launch the Device Server using
                **Wago personal_name**
- beacon_name: should coresponds to another Beacon object defined in yml that will
               define Wago mapping and host. 
               Refer to the documentation for creating the Musst bliss configuration
               [Musst](config_musst.md)

This is the most obvious solution where the device server configuration is at minimum.

Be aware that with this solution you will have to specify connection settings and
mapping `inside the Bliss wago client yml configuration.`

The other solution is to provide full configuration inside this yml file
(give the example contained in default_session):

```yaml
device:
- tango_name: id00/musst/1
  class: Musst
  properties:
personal_name: musst_test
server: Musst
```

- tango_name: is the Tango Fully Qualified Domain Name (FQDN) in the form *domain/family/member*
- personal_name: this will be the name you will use in the command line to launch the Device Server using
                **Wago personal_name**

### Bliss MusstDS as old C++ server replacement ###

If we want to use BLISS MusstDS as a replacement for an existing C++ server we just have to register the **Tango Server** through **Jive** or similar and than follow the example on first paragraph "Launching the device server".

After doing we will have to create/fill the properties:

And finally restarting the device server should do the job.


