# NHQ configuration

The Models NHQ 202M-206L HV supplies are a two channel high voltage version in a NIM chassis.

The `Nhq` controller class (`bliss.controllers.powersupply.nhq`) provides:

**2 SoftAxis (pseudo-axes)**:

- Output voltage setpoint on channel 'A' (using a ramp rate)

- Output voltage setpoint on channel 'B' (using a ramp rate)


**4 Counters**:

- Actual voltage on channel 'A' (tag: `voltage`)

- Actual current on channel 'A' (tag: `current`)

- Actual voltage on channel 'B' (tag: `voltage`)

- Actual current on channel 'B' (tag: `current`)


## Configuration example (yml)

```yml
- class: Nhq
  module: powersupply.nhq
  plugin: bliss
  name: nhq
  timeout: 10
  tcp:
    # we use the port configuration
    # 28319:raw:0:/dev/ttyRP19:9600 remctl  kickolduser NOBREAK 
    url: lid101:28319

  counters:
    - counter_name: iav
      channel: A
      tag: voltage
      mode: SINGLE
    - counter_name: iac
      channel: A
      tag: current
      mode: SINGLE
    - counter_name: ibv
      channel: B
      tag: voltage
      mode: SINGLE
    - counter_name: ibc
      channel: B
      tag: current
      mode: SINGLE

  axes:
    - axis_name: oav
      channel: A

    - axis_name: obv
      channel: B

```

## Presentation of the NHQ controller

Display information about the controller by typing its name in the shell.

```python

TEST_SESSION [2]: nhq
Gathering information from {'url': 'localhost:28319'}, please wait few seconds...

         Out [2]: === Controller nhq (sn481323 ver2.06) ===

                  Maximum voltage : 5000V
                  Maximum current : 2mA
                  Channel A state : ON @ -0.0V
                  Channel B state : ON @ 0.0V
```

The Nhq has two high voltage channels 'A' and 'B'. 

Display more information about each channel with the `.chA` and `.chB` properties.

```python
TEST_SESSION [3]: nhq.chA
         Out [3]: === Channel 'A' ===

                  Control     : RS232
                  Polarity    : negative
                  HV-ON switch: ON
                  KILL-ENABLE : OFF
                  INHIBIT     : inactive

                  Status      : ON (Output voltage according to set voltage)
                  Voltage     : -0.0V     (limit=90.0%)
                  Current     : 0.0A      (limit=20.0%)
                  Setpoint    : 0.0V
                  Ramp rate   : 40.0V/s
                  Current trip: 300.0

```

Read the actual current and voltage values of a channel with:

```python
TEST_SESSION [8]: nhq.chA.voltage                                                                                             
         Out [8]: 30.0
TEST_SESSION [9]: nhq.chA.current                                                                                             
         Out [9]: 0.000243
```


Set the output voltage to a target value (setpoint) with:

```python
TEST_SESSION [9]: nhq.chA.setpoint=80
```


The device will ramp the voltage up to the setpoint value at a given ramping rate (V/s).

```python
TEST_SESSION [12]: nhq.chA.ramprate                                                                                
         Out [12]: 40.0  
TEST_SESSION [7]: nhq.chA.status                                                                                          
         Out [7]: 'L2H' 
```

The `.status` property of a channel (`nhq.chA.status`) provides information about the ramping:

* `ON`: the actual voltage is equal to the voltage setpoint value (not ramping).

* `L2H`: the actual voltage is increasing to the voltage setpoint value (ramping).

* `H2L`: the actual voltage is decreasing to the voltage setpoint value (ramping).

* `TRP`: the high voltage has been cut because the actual current exceeded the current trip value (ramping aborted). 


Each channel can define a `current_trip` (e.g: `nhq.chA.current_trip=600`uA).

If the actual current exceed this value while ramping, the ramping is stopped and voltage set to zero.


If the communication with the NHQ hardware is too slow or unstable:

- `nhq.break_time`: set the minimum time between 2 characters (hardware property).

- `nhq._comm_delay`: set the wait delay between 2 successives commands.


## Scanning with the NHQ

For each channel, the NHQ provides a pseudo axis for the high voltage output and 2 counters to read the actual voltage and current.

These objects are exported in the session using the `counter_name` and `axis_name` defined in the YML configuration file.

```python
TEST_SESSION [16]: nhq.counters                                                                                              
         Out [16]: Namespace containing:
                   .iav
                   .iac
                   .ibv
                   .ibc
                                                                                                                     
TEST_SESSION [18]: nhq.axes                                                                                                
         Out [18]: Namespace containing:
                   .oav
                   .obv                      
```

For example, the high voltage of channel 'A' can be scanned using the pseudo axis 'oav'.

Between two points of the scan, the output voltage will be ramped using the actual `ramprate`.

In a scan command, counting on the NHQ will count on all four counters.

```python
TEST_SESSION [15]: ascan(oav,40,80,4,1,nhq)                                                                                 
         Out [15]: Scan(number=38, name=ascan, path=/home/pguillou/tmp/scans/test_session/data.h5) 

Scan 38 Tue Apr 21 11:19:18 2020 /home/pguillou/tmp/scans/test_session/data.h5 test_session user = pguillou
ascan oav 40 80 4 1

           #         dt[s]        oav[V]        iac[A]        iav[V]        ibc[A]        ibv[V]
           0             0            40      0.000122           -40             0             0
           1       5.99969            51      0.000152           -50             0             0
           2       12.0537            60      0.000184           -60             0             0
           3       18.3079            71      0.000213           -70             0             0
           4       24.4353            81      0.000243           -80             0             0

Took 0:00:35.375036
```


## Using a Nhq channel as a Regulation output 

The high voltage outputs of the NHQ can be used as an `ExternalOutput` of the Bliss Regulation framework.

A implementation of that class is already provided and can be imported like this:

```yml
- class: NhqOutput    
    module: powersupply.nhq
    plugin: bliss
    name: nhq_output_A
    device: $nhq.chA
    unit: V    
    ramprate: 10.0  #V/s     
```



```python
TEST_SESSION [10]: na=config.get('nhq_output_A')      
TEST_SESSION [11]: na 
         Out [11]:

    === ExternalOutput: nhq_output_A ===
    device: nhq.chA <bliss.controllers.powersupply.nhq.NhqChannel object at 0x7f1d4cfb8c50>
    current value: -40.000 V
    ramp rate: 10.0
    ramping: False
    limits: (None, None)
```