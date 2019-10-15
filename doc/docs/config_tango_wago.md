# Wago Device Server #

## Launching the device server ##

Let's make it easy and see how to launch the device server:

```
(base) user@beamline:~/bliss$ conda activate bliss
(bliss) user@beamline:~/bliss$ Wago -?
Can't build connection to TANGO database server, exiting
(bliss) user@beamline:~/bliss$ export TANGO_HOST=localhost:20000
(bliss) user@beamline:~/bliss$ Wago -?
usage :  Wago instance_name [-v[trace level]] [-nodb [-dlist <device name list>]]
Instance name defined in database for server Wago :
        wago_tg_server
(bliss) user@beamline:~/bliss$ Wago wago_tg_server
Unknown exception while trying to fill database cache...
Ready to accept request
```

## Configuration ##

The configuration of this device server is written inside Beacon as
an yaml file, here we have the example contained by test_configuration.

```yaml
device:
- tango_name: 1/1/wagodummy
  class: Wago
  properties:
    Iphost: localhost
    Protocol: TCP
    config:
    - 750-504, foh2ctrl, foh2ctrl, foh2ctrl, foh2ctrl
    - 750-408, foh2pos, sain2, foh2pos, sain4
    - 750-408, foh2pos, sain6, foh2pos, sain8
    - 750-408, pres
    - 750-469, esTf1, esTf2
    - 750-469, esTf3, esTf4
    - 750-469, esTr1, esTr2
    - 750-469, esTr3, esTr4
    - 750-517, intlckf1, intlckf2
    TCPTimeout: 1000
personal_name: wago_tg_server
server: Wago
```

- tango_name: is the Tango Fully Qualified Domain Name (FQDN) in the form *domain/family/member*
- Iphost: the *host* of your wago, the port is assumed to by 502 but can be specified in a *host:port* form.
- config: a list where we have a line for each add-on module plugged to the Wago main module.
          You will put the hardware code followed by *logical names* that you want to assign to input/output
- personal_name: this will be the name you will use in the command line to launch the Device Server using
                **Wago personal_name**

