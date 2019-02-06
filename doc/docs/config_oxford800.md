# Oxford 800

!!! note
    The communication library is not part of bliss. You have to install first liboxford800.

This model has a network connection in 10 Mbits Half Duplex.  It work
nicely in DHCP, you can find the MAC address on the device screen in
the network menu.  As soon as the controller is connected to the
network, it starts to send udp packet. So to check it's connectivity
run this command.

```bash
python -c "from bliss.controllers.temperature.oxfordcryo import oxford800;oxford800.ls_oxford800()"
```

This command should return the list of all oxford 800 connected to your local network.
i.e:

```bash
Oxford 800 (id10oxford800.esrf.fr -> ['160.103.30.84'])
	 not updated since 0.06
	 Device: Cryostream
	 mac: b'00-00-0C-01-01-36'
	 gaz set point: 294.8
	 gaz temp: 294.81
	 gaz error: -2.03
	 run mode code: 6,Shut down with error
	 phase id: 3,Hold
	 ramp rate: 0
	 target temp: 294.3
	 evap temp: 294.88
	 suct temp: 295.39
	 remaining: 65534
	 gas flow: 65534
	 gas heat: 0
	 evap heat: 0
	 suct heat: 0
	 line pressure: 655.34
	 alarm code: 4,Flow rate fail
	 run time: 1
```

The **cryoname** will be used for the yaml configuration.

## YAML configuration file example

```YAML
- class: Oxford800
  module: oxfordcryo.oxford800
  cryoname: id10oxford800
  outputs:
    - name: cryostream
      low_limit:  80
      high_limit: 500
      tango_server: id10_eh2
```
