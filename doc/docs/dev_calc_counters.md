
# Calculational Counters

Calculational Counters can be typically used:

* to do computations on raw values.
* to agregate counters.

A calculational counter transforms `N` inputs into `M` outputs.

cf:

* `tests/scans/test_calc_counter.py`
* `tests/test_configuration/simulation_calc_counter.yml`
* `bliss/controllers/simulation_calc_counter.py`

A Calculational Counter Controller inherits from `CalCounterControler`.

In case of using Channels instead of Counter as data source, **Calculation
Channels** have to be used. This is typically the case when doing calculation
objects under MUSST channels



## To use a Calculational Counter Controller

Configuration can be done in YML of on-the-fly

**tags** are the roles of each counter, they can be used to identify counter in
calculation function.

configuration example:
```yaml
- plugin: bliss
  module: simulation_calc_counter
  class: MeanCalcCounterController
  name: simul_calc_controller2
  inputs:
    - counter: $simu1.counters.deadtime_det0
      tags: data1

    - counter: $simu1.counters.deadtime_det1
      tags: data2

  outputs:
    - name: out2
```


## To create a Calculational Counter Controller

To create a Calculation Counter Controller, the main task is to provide the
calculation function named `calc_function()` to compute input values.

This function takes `input_dict` as a parameter and must return a dictonary of
the computed values.

Calculations are made on `numpy` arrays, so all operations must be numpy
compatible.

If there is no **tags** defined, inputs are indexed by counter names.


### Example: Mean calculation

Example for a Calculational Counter to return the mean value from 2 or more
existing counters(real ou calc) `bliss/controllers/simulation_calc_counter.py`:

```python
from bliss.controllers.counter import CalcCounterController

class MeanCalcCounterController(CalcCounterController):
    def calc_function(self, input_dict):

        csum = 0

        # example of self.inputs (2 input counters):
        #   [<....SimulationCounter object at 0x7f9da11f8350>,
        #    <....SimulationCounter object at 0x7f9da12537d0>]
        #
        # example of input_dict: {'data1': array([1.]), 'data2': array([1.])}
        #   * indexed by 'data1' and 'data2' tags.
        # example of self.outputs (1 output counter):
        #   [<bliss.common.counter.CalcCounter object at 0x7f03900a4e10>]
        #
        # example of self.tags: {'sim_ct_1': 'data1',
        #                        'sim_ct_2': 'data2',
        #                        'out1':     'out1'}

        # len(list(input_dict.values())[0])  is the number of points to compute.

        for cnt in self.inputs:
            csum += input_dict[self.tags[cnt.name]]

        csum = csum / float(len(self.inputs))

        return {self.tags[self.outputs[0].name]: csum}
```


* `self.inputs` : list of counters or calc counters.
* `self.outputs`: list of calc counters.
* `input_dict`: values of inputs to compute.

input dict indexed by `tags`

calculation is performed on maximum number of elements available for all inputs.

tags are "roles" ?

if no tag -> use counter names

CalcCounter without input counter ???


calculation is performed on a 1 to 1 element basis: to reduce the number of
points of an input, an index on read data (`self.data`) must be maintained.

corresponding YAML config:

```yaml
- plugin: bliss
  module: simulation_calc_counter
   #   package ???
  class: MeanCalcCounterController
  name: simul_calc_controller
  inputs:
    - counter: $diode
      tags: data1

    - counter: $diode2
      tags: data2

  outputs:
    - name: out1
```

Number of inputs can be given by the number of counters in the config ???





```python
def test_calc_counter_from_config(default_session):

    cc1 = default_session.config.get("simul_calc_controller")  # ### GNI ??? on utilise le controller ?
    cc2 = default_session.config.get("simul_calc_controller2")

    roby = default_session.config.get("roby")

    sc = ascan(roby, 0, 10, 10, 0.1, cc1, cc2)

    assert numpy.array_equal(
        sc.get_data()["out1"],
        (sc.get_data()["diode"] + sc.get_data()["diode2"]) / 2.
    )

    assert numpy.array_equal(
        sc.get_data()["out2"],
        (sc.get_data()["deadtime_det0"] + sc.get_data()["deadtime_det1"]) / 2.,
    )
```













## Example: BPM


```python
from bliss.controllers.counter import CalcCounterController

class BpmCalcCounter(CalcCounterController):

    def calc_function(self, input_dict):

        # BPM calculation.
        #    __________________________
        #   |_upper_left_|_upper_right_|   ↑
        #   |------------|-------------|
        #   | lower_left | lower_right |   y  x→
        #    ---------------------------

        up_left   = input_dict["up_left"]
        up_right  = input_dict["up_right"]
        low_right = input_dict["low_right"]
        low_left  = input_dict["low_left"]

        csum = up_left + up_right + low_right + low_left

        bpm_x = ((up_left + low_left) - (up_right + low_right)) / csum
        bpm_y = ((up_left + up_right) - (low_right + low_left)) / csum

        bpm_values = {}
        bpm_values["bpmi"] = csum
        bpm_values["bpmx"] = bpm_x
        bpm_values["bpmy"] = bpm_y

        # print(f"CCC -- calc_function >>>> {bpm_values} ")

        return bpm_values

```



## Data length change

I previous examples, the length of received data is not considered: the function
produces the same length of outputs than the length of inputs received.

In case a scan mix counters with different triggering modes, it can be useful to
remove a point of the scan and/or to re-arrange the points.

see figure ???

cf:

`self.data[cnt.name]`

`self.data_index[cnt.name]`

### Example: zapline reduction



## Data shape change

1D -> 2D

### example: MCA roi maps





