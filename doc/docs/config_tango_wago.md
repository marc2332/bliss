# Wago Device Server #

## Launching the device server ##

Let's make it easy and see how to launch the device server:

```
(base) user@beamline:~/bliss$ conda activate bliss
(bliss) user@beamline:~/bliss$ export TANGO_HOST=localhost:20000
(bliss) user@beamline:~/bliss$ Wago -?
usage :  Wago instance_name [-v[trace level]] [-nodb [-dlist <device name list>]]
Instance name defined in database for server Wago :
        wago_tg_server
(bliss) user@beamline:~/bliss$ Wago wago_tg_server
Ready to accept request
```

## Different run possibilities ##

The Wago Device server can be run:

- with Beacon
- as a replacement of Taco/Tango C++ device servers (having working MySql and DatabaseDS instances)


## Configuration ##

### With Beacon ###

The configuration of this device server is written inside Beacon as
an yaml file, here we have the example:

```yaml
device:
- tango_name: 1/1/mywago
  class: Wago
  properties:
    beacon_name: mywago
personal_name: wago_mywago
server: Wago
```

- tango_name: is the Tango Fully Qualified Domain Name (FQDN) in the form *domain/family/member*
- personal_name: this will be the name you will use in the command line to launch the Device Server using
                **Wago personal_name**
- beacon_name: should coresponds to another Beacon object defined in yml that will
               define Wago mapping and host. 
               Refer to the documentation for creating the Wago bliss configuration
               [Wago](config_wago.md)

This is the most obvious solution where the device server configuration is at minimum.

Be aware that with this solution you will have to specify connection settings and
mapping `inside the Bliss wago client yml configuration.`

In particular be sure that you specify both connection types:

```yml
modbustcp:
    url: host:port
tango:
    url: tango://domain/family/member
```

This will instruct the Device Server to connect to the proper modbustcp host, so when launching it using for example:
`Wago wago_mywago` it will connect to Wago through modbustcp.
Instead when instantiating a client in Bliss shell or script they will use `tango` connection.

The other solution is to provide full configuration inside this yml file
(give the example contained in default_session):

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

### Bliss WagoDS as old C++ server replacement ###

If we want to use Bliss WagoDS as a replacement for an existing C++ server we just have to register the **Tango Server** through **Jive** or similar and than follow the example on first paragraph "Launching the device server".

After doing we will have to create/fill the properties:

- Iphost
- config
- Protocol (not necessary, default value is TCP and is always the same)
- TCPTimeout (default value is 1000ms)

And finally restarting the device server should do the job.


