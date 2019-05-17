
# BLISS simulation devices configuration

This chapter explains how to configure simulation BLISS devices:

* motor
* counter
* MCA
* Lima Camera

Such simulated devices can be used to: train users, test procedures or
to perform unit tests


## Motor

To create a simulation motor, you have to use the `mockup` class:

    controller:
      class: mockup
      axes:
         - velocity: 1
           name: simot1
           acceleration: 10
           steps_per_unit: 100

Do not forget to declare the plugin to use in a ` __init__.yml ` file:

     plugin: emotion

This simulation axis can now be used by BLISS:

    BLISS [5]: sm = config.get("simot1")
    BLISS [6]: sm.position()
      Out [6]: 2.0
    BLISS [7]: sm.move(4)
    BLISS [8]: sm.position()
      Out [8]: 4.0


## Calculational motor


```yaml
controller:
    class: calc_motor_mockup
    module: mockup
    axes:
        -
          name: $m1
          tags: real real_mot
        -
          name: calc_mot
          tags: calc_mot
          s_param: 3.1415
```


## Counter

A pretty generic simulation counter is provided by
`simulation_counter` module to define a fake counter.

This fake counter is usable in a `ct` or in a [default
scan](scan_default.md).

It returns floats numbers that can be:

* constant
* random
* following a gaussian distribution

If included in a scan (except timescan/loopscan without predefined
number of points), it returns values according to a user defined
distribution:

* FLAT (constant value)
* GAUSSIAN

If included in a `ct` or a `timescan`, it returns either a constant
value.

Returned values can be altered by adding a random "noise".

### Parameters

* `<distribution>`:  'GAUSSIAN' | 'FLAT'
* `<noise_factor>`:
    * `>= 0.0`
    * add a random noise to the distribution
    * 0 means 'no random noise added'
    * noise added is only positive.
* `<height_factor>`:
    * `>= 0.0`
    * multiplication factor to adjust height (Y)

Parameters if using GAUSSIAN:

* `<mu_offset>`: shitfs mean value by `<mu_offset> `(X-offset)
* `<sigma_factor>`: standard deviation adjustement factor.


!!! note

    TODO: adding an option to be able to furnish to counter a
    user-defined array for tests on a deterministic curve.


### Examples

`sim_ct_1` counter is configured to generate a gaussian curve:

* centered in 0 (mu = 0.0)
* with a standard deviation (fwhm = ~2.35 * sigma) of 1 (sigma_factor = 1.0)
* scaled in height by 100 ( height_factor: 100.0)

NB: the real height depends also on the sigma value.


```yaml
-
  name: sim_ct_1
  plugin: bliss
  class: simulation_counter
  distribution: GAUSSIAN
  mu_offset: 0.0
  sigma_factor: 1.0
  height_factor: 100.0
  noise_factor: 0.0
```


`sim_ct_2` counter is configured to generate a noisy gaussian curve:

* centered in -1 (mu = -1.0)
* with a standard deviation of 0.4 (sigma_factor = 0.4) (narrower than sim_ct_1's curve)
* scaled in height by 100 ( height_factor: 100.0)
* with a noise factor of 0.1
```yaml
-
  name: sim_ct_2
  plugin: bliss
  class: simulation_counter
  distribution: GAUSSIAN
  mu_offset: -1.0
  sigma_factor: 0.4
  height_factor: 100.0
  noise_factor: 0.1
```

`sim_ct_3` counter is configured to depict a constant value:

* of value 12.0 ( height_factor: 12.0)
* without noise (noise_factor: 0.0)

```yaml
-
  name: sim_ct_3
  plugin: bliss
  class: simulation_counter
  distribution: FLAT
  height_factor: 12.0
  noise_factor: 0.0
```

`sim_ct_4` counter is configured to depict a random value:

* with a base line of 12.0 ( height_factor: 12.0)
* with positive noise (noise_factor: 1.01)

```yaml
-
  name: sim_ct_4
  plugin: bliss
  class: simulation_counter
  distribution: FLAT
  height_factor: 12.0
  noise_factor: 1.01
```


## MCA

To create a simulation MCA, just use `SimulatedMCA` class:

    name: simul_mca
    module: mca
    class: SimulatedMCA
    plugin: bliss

## Lima Device

Any Tango lima device (for example: **id99/limaccd/simul_cam**) server
can be used in a BLISS session.

Make sure the server is well running. If you don't have a camera
installed, use the Lima Simulator.

!!! note

    At ESRF, see:
    http://wikiserv.esrf.fr/bliss/index.php/Lima_ds_installation#Device_Servers


The corresponding YAML configuration file looks like:

```yaml
name: simul_cam
class: Lima
tango_url: id99/limaccd/simul_cam
```

