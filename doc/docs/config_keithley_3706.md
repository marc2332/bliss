
# Keithley 3706

Keithley 3706 is a multi-channels multimeter.
It is used in DCM to monitor 60 pt100 sensors.

!!! note
    As the K3706 is not a regulator but only a reading device, it is not
    (for now) included in the regulation framework.


http://wikiserv.esrf.fr/bliss/index.php/Keithley_3706

Configuration example:

    class: Keithley3706
    name: k37dcm
    tcp:
      url: k3706dcm.esrf.fr
    counters:
      - counter_name: X1111_7
        slot: 1
        channel: 1
      - counter_name: X1111_8
        slot: 1
        channel: 2

!!! note
    For now, all channels of the 4 slots are read at each count. It takes
    around 12 seconds.

Usage notes:
* each slot musst be initilized after a reboot of the device
* To perform a reading, a 'Programm' has to be ran



