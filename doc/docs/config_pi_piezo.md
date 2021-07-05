## Configuring a PI piezo controller

This chapter explains how to configure a piezo controller from
Physical Instrument company.

This configuration should be common to the following models:

* PI E-753 - 754
* PI E-517 - 518
* PI E-712
* PI E-727

### Supported features

Encoder | Shutter | Trajectories
------- | ------- | ------------
YES	    | NO      | YES (E-712)

### YAML configuration file example
```yaml
controller:
  class: PI_E753
  tcp:
     url: e754id42:50000
  encoders:
    - name: e754m0_enc
      steps_per_unit: 1
      tolerance: 0.1
  axes:
      - acceleration: 1.0
        backlash: 0
        high_limit: null
        low_limit: null
        name: e754m0
        offset: 0
        encoder: $e754m0_enc
        steps_per_unit: 1
        tolerance: 0.1
        velocity: 11
        tango_server: e754m0
```

!!! note
If `port` is not specified in `url`, e753 uses by default port `50000`.

!!! warning
    The PI controller only accepts a single tcp connection

If a controller needs to be accessible in multiple sessions simultaneously
the tcp connection needs to be proxied as follows:

```yaml
controller:
  class: PI_E753
  tcp-proxy:
    tcp:
       url: e754id42:50000
```


## Recorder

For 712 753.

Real-time data recorder is able to record several input and output signals
(e.g. current position, sensor input, output voltage) from different data
sources (e.g. controller axes or input and output channels).

POSSIBLE DATA RECORDER TYPE:

* `TARGET_POSITION_OF_AXIS`
* `CURRENT_POSITION_OF_AXIS`
* `POSITION_ERROR_OF_AXIS`
* `CONTROL_VOLTAGE_OF_OUTPUT_CHAN`
* `DDL_OUTPUT_OF_AXIS`
* `OPEN_LOOP_CONTROL_OF_AXIS`
* `CONTROL_OUTPUT_OF_AXIS`
* `VOLTAGE_OF_OUTPUT_CHAN`
* `SENSOR_NORMALIZED_OF_INPUT_CHAN`
* `SENSOR_FILTERED_OF_INPUT_CHAN`
* `SENSOR_ELECLINEAR_OF_INPUT_CHAN`
* `SENSOR_MECHLINEAR_OF_INPUT_CHAN`
* `SLOWED_TARGET_OF_AXIS`

The gathered data is stored (temporarily) in "data recorder tables".

* `set_recorder_data_type(*motor_data_type)`: Configure the data recorder

    `motor_data_type` should be a list of tuple with motor and datatype
     i.e: motor_data_type=[px, px.CURRENT_POSITION_OF_AXIS,
                           py, py.CURRENT_POSITION_OF_AXIS]

Example:
```python

mot.controller.set_recorder_data_type(motor, motor.VOLTAGE_OF_OUTPUT_CHAN)

mot.controller.start_recording(mot.controller.WAVEFORM, recorder_rate)
```

## Wave motion generator

For 753.

A "wave generator" allows to produce "waveforms" ie.user-specified patterns.

This feature is especially important in dynamic applications which require
periodic, synchronous motion of the axes. The waveforms to be output are stored
in "wave tables" in the controllers volatile memory—one waveform per wave
table. Waveforms can be created based on predefined "curve" shapes. This can be
sine, ramp or single scan line curves. Additionally you can freely define curve
shapes.

During the wave generator output, data is recorded in "record tables" on the
controller.

Example:
```python
mot.run_wave(wavetype, offset, amplitude, nb_cycles, wavelen)
```

* `wavetype`: str: `"LIN"` or `"SIN"`
* `offset`: float: motor displacement offset
* `amplitude`: float: motor displacement amplitude
* `nb_cycles`: int: the number of times the motion is repeated
* `wavelen`: float: time in second that should last the motion


## Trajectories

For E712.

## Switch

For E712.


## Examples

ID11 example for stress-rig motor combining wave generator and recorder.

```python
def stress_run_display(wavetype, offset, amplitude, nb_cycles, wavelen, recorder_rate=None):
    if STRESS_RIG_MOTOR is None:
        raise RuntimeError("First call init")

    mot = STRESS_RIG_MOTOR
    # Starts the recorder when the trajectory starts
    mot.controller.start_recording(mot.controller.WAVEFORM, recorder_rate=recorder_rate)

    def refresh_display(data):
        current_index = len(data) if data is not None else 0
        ldata = mot.controller.get_data(from_event_id=current_index)
        if ldata is None or len(ldata) == 0:
            return data
        if data is not None:
            data = numpy.append(data,ldata)
        else:
            data = ldata

        x,y,y2 = (data[name] for name in data.dtype.names)
        #p.plot(data=y,x=x)
        p.plot(data={'target':y,'current':y2},x=x)
        return data

    # Get flint
    f = flint()
    #Create the plot
    p = f.get_plot(plot_class="plot1d", name="stress", unique_name="pi_stress")
    data=None
    with mot.run_wave(wavetype, offset, amplitude, nb_cycles, wavelen):
        while not mot.state.READY:
            current_index = len(data) if data is not None else 0
            data = refresh_display(data)
            if current_index == len(data):
                gevent.sleep(1)

    #last display
    refresh_display(data)
```
