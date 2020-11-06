# Oxford 800

!!! note
    The communication library is not part of bliss. You have to install first liboxford800.
    To Install the library, you must clone the gitlab project and pip install it:
       $ git clone https:/gitlab.esrf.fr/bliss/liboxford800
       $ . blissenv
       $ (bliss_dev) pip install -e .

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

The oxford800 hostname will be used to set **cryoname** parameter of the YML file

## YAML configuration file example

```YAML
- class: Oxford800
  plugin: temperature
  module: oxfordcryo.oxford800
  cryoname: id10oxford800
  outputs:
    - name: cryostream
      low_limit:  80
      high_limit: 500
      unit: K
      tango_server: id10_eh2
```

## Usage

As for any temperature controller you can import the new controller in your session and start ramping and read the current temperature:

```python

BLISS [1]: ox=config.get('cryostream')
BLISS [2]: ox
  Out [2]: Oxford 800 (id10oxford800.esrf.fr -> ['160.103.30.84'])
                 not updated since 0.42
                 Device: Cryostream
                 mac: b'00-00-0C-01-03-7D'
                 gaz set point: 300.0
                 gaz temp: 300.01
                 gaz error: -0.01
                 run mode code: 3,Running
                 phase id: 3,Hold
                 ramp rate: 0
                 target temp: 300.0
                 evap temp: 80.07
                 suct temp: 292.44
                 remaining: 0
                 gas flow: 65534
                 gas heat: 55
                 evap heat: 55
                 suct heat: 0
                 line pressure: 655.34
                 alarm code: 0,No errors or warnings
                 run time: 210

# read the current temperature
BLISS [6]: ox.read()
  Out [6]: 291.23

BLISS [8]: ct(0, ox)

         cryostream[K]  =  284.830      (    inf     /s)    cryostream

   Took 0:00:00.691639[s]

#read the ramprate
BLISS [7]: ox.ramprate()
  Out [7]: 360

# start a ramp
BLISS [10]: ox.ramp(
                    ramp(new_setpoint=None, ramp_rate=None)

```
