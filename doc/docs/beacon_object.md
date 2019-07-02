# Linked Yaml config file with settings

Behavior of parameters of objects used in BLISS is a subtle entanglement of
*configuration* (YAML file), *in-memory configuration* and *settings* (Redis
database).

**BeaconObject** helper aims to standardize and to simplify management of
parameters in BLISS objects usage.

## `BeaconObject`

This mechanism is based on `bliss.config.beacon_object.BeaconObject` class.

A new BLISS object must inherit from `BeaconObject` class and a **beacon
configuration node** be passed as first argument.

```python
[...]
class SimpleAxis(BeaconObject):
    def __init__(self, name, config):
        BeaconObject.__init__(config)
[...]
```

Inheriting of `BeaconObject` class, adds to the object instantiating this class:

* `.config` property:
    * it returns the *in-memory configuration*
    * it's a `Node` object that depict YAML configuration at last reload (or session restart)
    * it is updated only on a session start or when calling `.apply_config(reload=True)`

```python
DEMO [8]: type (controller_setting1.config)
 Out [8]: <class 'bliss.config.static.Node'>

DEMO [9]: controller_setting1.config
 Out [9]: filename:<demo/hack/simple_axis.yml>,plugin:'bliss',
          {'name': 'controller_setting1', 'close_loop': True,
           'velocity': 1.1, 'settling_window': 25, 'encoder_divider': 100}
```

* `.settings` property:
    * it returns a `HashObjSetting` containing the settings values.
    * at first use, initializes all parameters by calling all the `.setter`
      methods decorated by `@BeaconObject.property`

```python
DEMO [5]: controller_setting1.settings
 Out [5]: <HashObjSetting name=controller_setting1:settings value={
              'close_loop': True, 'encoder_divider': 100,
              'encoder_output_enable': True, 'velocity': 1.1,
              'settling_window': 25}>
```

* `.apply_config(reload=False)` method:
    * it applies *in-memory configuration* parameters to the controllers and updates settings.
    * if `<reload>` is set to `True`, configuration is re-read from YAML file.

It also ensures *at initialization* that all defined settings parameters are
applied to the controller.

A parameter must be defined as a property using the `@BeaconObject.property`
decorator.

```python
[...]
@BeaconObject.property(default=True)
def close_loop(self):
    return self.controller.is_close_loop_on()

@close_loop.setter
def close_loop(self, on_off):
    self.controller.activate_close_loop(on_off)
[...]
```

On the first initialization, values defined in *in-memory configuration* will be
used to initialize the controller and, in case of success, will be used to
create *settings*.

Behavior of the parameters can be constrained by passing some of the following
arguments to the decorator:

* `must_be_in_config` (Boolean): makes parameter mandatory in config
* `default`: default value to use if parameter is not defined in config
* `only_in_config` (Boolean): parameter must be defined in the static
  configuration and cannot be changed
* `priority` (int): sets order of initialization.
    * the higher the number is, the lower the priority is.

!!! note "Note: config is at the same level than object"
    The config must be at the same level than the object. This implies the
    need to deal with more than one `BeaconObject` in case of hierarchical
    configuration.

### `lazy_init`
lazy_init : the `lazy_init` decorator will ensure that ALL settings are set (ie
all .setter methods will be called) before the execution of the decorated
method.

### Errors
In case or mis-usage of a parameter, a `RuntimeError` exception is raised when
any of the parameters is used.

### Reload of the configuration

* `apply_config()`:
    * applies current *in-memory configuration* parameters to the controller (by
      calling all `.setters` methods)
    * sets settings to parameters values if success

* `apply_config(reload=True)`:
    * reloads parameters from YAML file to *in-memory configuration*
    * applies current *in-memory configuration* parameters to the controller (by
      calling all `.setters` methods)
    * sets settings to parameters values if success

A `name` in configuration file is mandatory to be able to retrieve the
corresponding node and then to reload properly the configuration.


## Example

```python
from bliss.config.beacon_object import BeaconObject

# ctrl() depicts interactions with an typical hardware.
class ctrl():
    def __init__(self):
        pass

    def read_velocity(self):
        return self._velo

    def set_velocity(self, new_velocity):
        print("new_velocity=", new_velocity)
        self._velo = new_velocity

    def is_close_loop_on(self):
        return self._cl

    def activate_close_loop(self, onoff):
        self._cl = onoff
        print("closed loop is", onoff)

    def get_settling_window(self):
        return self._sw

    def set_settling_window(self, new_sw):
        self._sw = new_sw
        print("set_settling_window to", new_sw)

    def set_encoder_output_enable(self, onoff):
        print("encoder_output_enable=", onoff)

    def set_encoder_divider(self, ed_value):
        self._ed = ed_value
        print("encoder divider set to", self._ed)

    def get_encoder_divider(self):
        return self._ed

    def move(self, target):
        print("moving to ", target)

class SimpleAxis(BeaconObject):
    def __init__(self, name, config):
        BeaconObject.__init__(self, config)

        self.controller = ctrl()

    @BeaconObject.property(must_be_in_config=True)
    def velocity(self):
        return self.controller.read_velocity()

    @velocity.setter
    def velocity(self, new_velocity):
        self.controller.set_velocity(new_velocity)

    @BeaconObject.property(default=True)
    def close_loop(self):
        return self.controller.is_close_loop_on()

    @close_loop.setter
    def close_loop(self, on_off):
        self.controller.activate_close_loop(on_off)

    @BeaconObject.property(priority=2, only_in_config=True)
    def settling_window(self):
        return self.controller.get_settling_window()

    @settling_window.setter
    def settling_window(self, value):
        self.controller.set_settling_window(value)

    @BeaconObject.property(priority=1, default=True)
    def encoder_output_enable(self):
        return self.controller.get_encoder_output_enable()

    @encoder_output_enable.setter
    def encoder_output_enable(self, value):
        self.controller.set_encoder_output_enable(value)

    @BeaconObject.property(default=421)
    def encoder_divider(self):
        return self.controller.get_encoder_divider()

    @encoder_divider.setter
    def encoder_divider(self,value):
        self.controller.set_encoder_divider(value)

    @BeaconObject.lazy_init
    def move(self, to_position):
        self.controller.move(to_position)
```

This example uses all the features provided by `BeaconObject` class.


* **velocity** with the `must_be_in_config` argument set to True, it will checked
  that **velocity** is defined in the static configuration.

* **close_loop** the `default` value will be use if **close_loop** is not
  defined in the static configuration.

* **settling_window** as it `only_in_config`, this parameter must be defined in
  the static configuration and cannot be changed. The setter property will only
  be used at init. The getter always read the controller.

* **encoder_output_enable** here we set the initialization `priority` order.
  properties with lower `priority` are called before than high `priority` during
  the initialization phase.

* **encoder_divider** if not defined in the static configuration, this
  parameters will be read from the controller at the first init or when the
  `apply_config()` method will be called.

* before calling the `move()` method, it is checked that the controller is
  initialized with the settings parameters.


## Behavior of BeaconObject

```yaml
- class: SimpleAxis
  plugin: bliss
  obj:
    - name: controller_setting1   # all parameters are valid and defined
      close_loop: True
      velocity: 1.1
      settling_window: 25
      encoder_divider: 100

    - name: controller_setting2  # test must_be_in_config
      # 'velocity' and 'settling_window' are not defined
      mode: fixed
      reading_speed: slow  # unkown parameter
      close_loop: True

    - name: controller_setting3  # test default (421 for 'encoder_divider')
      close_loop: True
      velocity: 1.1
      settling_window: 25
```

With the previous controller and this configuration, the usage of objects will
produce the following behavior:

Settings are initialized:

* at first use of `settings` property.
* at first call to a method decorated by `@BeaconObject.lazy_init`


!!! note
    This initialization can occur in the completion process as it access properties.


```python
# session just restarted
DEMO [1]: pprint.pprint(controller_setting1.settings.get_all())
new_velocity= 1.1
closed loop is True
encoder divider set to 100
encoder_output_enable= True   <----- Priority = 1
set_settling_window to 25     <----- Priority = 2
{'close_loop': True,
 'encoder_divider': 100,
 'encoder_output_enable': True,
 'settling_window': 25,
 'velocity': 1.1}

DEMO [2]: pprint.pprint(controller_setting1.settings.get_all())
{'close_loop': True,
 'encoder_divider': 100,
 'encoder_output_enable': True,
 'settling_window': 25,
 'velocity': 1.1}
```


```python
# session just restarted
DEMO [1]: controller_setting3.move(4)
new_velocity= 1.1
closed loop is True
encoder divider set to 421
encoder_output_enable= True
set_settling_window to 25
```

!!! note
    `encoder_output_enable` (priority 1) is set *before*
    `set_settling_window` (priority 2) that has a *higher* priority number (ie:
    lower priority)

### Errors


* `must_be_in_config`: `settling_window`, `velocity` are not defined in config
  of `controller_setting2`.

```python
DEMO [1]: pprint.pprint(controller_setting2.settings.get_all())
RuntimeError: For device controller_setting2
              configuration must contains {'settling_window', 'velocity'}
```



* `default`: Default value of 'encoder_divider' is 421 and it is not defined in
  config.

```python
# session just restarted
DEMO [1]: pprint.pprint(controller_setting3.settings.get_all())
new_velocity= 1.1
closed loop is True
encoder divider set to 421
encoder_output_enable= True
set_settling_window to 25
{'close_loop': True,
 'encoder_divider': 421,
 'encoder_output_enable': True,
 'settling_window': 25,
 'velocity': 1.1}
```

* `only_in_config`: `settling_window` must not be changed.


```python
DEMO [2]: controller_setting3.settling_window
 Out [2]: 25

DEMO [3]: controller_setting3.settling_window = 44
RuntimeError: parameter settling_window is read only
```

```python
DEMO [4]: controller_setting3.reading_speed
AttributeError: 'SimpleAxis' object has no attribute 'reading_speed'
```

