# Counters

Counters are BLISS objects intended to be read during a count or step
by step scan as well as during a continuous scan.

Such objects have then to follow a minimal API to be usable in
standard scans.


## Sampling or Integrating counter ?

A *sampling counter* obtains readout values "*on the
fly*" with just a read command:

* `read()`

BLISS examples:

* tango BPM
* Wago
* Keller gauges

An *integrating counter* processes readout values
according to a defined sequence, typically:

* `prepare()`
* `start()`
* `stop()`

BLISS examples:

* Lima ROI and BPM


a custom Acquisition device can be created in case of:

* non-standard device interfacing
    * ex: flex.py
* mix of data types : spectrum and scalars



### Counters classes

Hierarchy of BLISS classes related to counters.

![Screenshot](img/counter_classes_paths.svg)


## Group read
Both IC and SC provide mechanism to perform *group read*s in order to
read many counters at once, if they belong to a common controller, able
to read all channels at once.


## Sampling counter

Depending on the number and the way how channels of the controller are
managed, different designs can be used.

### example 1

A simple 1 channel-counter.

YML configuration:

    plugin: bliss
    class: EMH
    name: emeter2
    unit: volt
    tcp:
       url: em

In this example, BLISS controller has:

* to deal with connection (TCP)


### example 2 : EMH

A controller with multiple channels.

EMH is a 4chan electrometer.

YML configuration:

    plugin: bliss
    class: EMH
    name: emeter2
    unit: volt
    tcp:
       url: emeter2.esrf.fr
    counters:
    - counter_name: e1
      channel: 1
    - counter_name: e2
      channel: 2

!!! note
    In this example, keyword `counter_name` is used instead of
    `name` to avoid to load automatically the counters objects in
    BLISS sessions.


This example BLISS controller has:

* to deal with the connection (TCP)
* to manage channels (returned by `counters()` property)
* to allow a grouped reading of all channels.

NB: the controller file name must be in lower case.

Example from `emh.py`:

    class EmhCounter(SamplingCounter):
        def __init__(self, name, controller, channel, unit=None):
    
            SamplingCounter.__init__(self, name, controller)
            #                                    ref to the controller
            # the reading of many counters depending on the same
            # controller will be performed using controller.read_all() function
    
            self.channel = channel
            self.unit = unit
    class EMH(object):
        """
        ESRF - EM#meter controller
        """
        def __init__(self, name, config):
    
            self.name = name
            self.bliss_config = config
    
            self.comm = get_comm(config, TCP, eol='\r\n', port=5025)
            # port number is fixed for this device.

            self.counters_list = list()
            for counter_conf in config.get("counters", list()):
                unit = counter_conf.get_inherited("unit")
                counter = EmhCounter(counter_conf["counter_name"],
                                     self,
                                     counter_conf["channel"], unit)
                self.counters_list.append(counter)
    
        @property
        def counters(self):
            return counter_namespace(self.counters_list)
    
        def read_all(self, *counters):
            curr_list = self.get_currents()
            vlist = list()
    
            for counter in counters:
                vlist.append(curr_list[counter.channel - 1])
    
            return vlist

### Sampling counter statistics

Sampling counters read as many samples as possible from the connected hardware
in the specified counting time and return, amongst others, an average value
(default mode, see below for details). Additionally, some basic statistics of 
the sampling process are calculated on the fly, which are accessible after the 
count through the `.statistics` property.

```
    TEST_SESSION [1]: diode.mode     
             Out [1]: <SamplingMode.MEAN: 1>

    TEST_SESSION [2]: ct(1,diode)    
    
      diode = 8.03225806451613 ( 8.03225806451613/s)
        
    TEST_SESSION [3]: diode.statistics      
             Out [3]: SamplingCounterStatistics( mean=8.032, N=93,
                                                 std=55.96, var=3132.16, 
                                                 min=-98.0, max=100.0, 
                                                 p2v=198.0, count_time=1, 
                                                 timestamp='2019-07-26 10:13:25')
```
The values available in `SamplingCounterStatistics` are

 - `mean`: Mean value  $\bar x = \frac {\sum_{j=1}^n x_j}{n}$
 - `var`: Variance  $\sigma^2 = \displaystyle\frac {\sum_{i=1}^n (x_i - \bar x)^2}{n}$
 - `std`: Standard deviation $\sigma = \sqrt{\sigma^2}$
 - `min`: Minimum value $x_{min}$
 - `max`: Maxium value $x_{max}$
 - `p2v`: Peak to valley $x_{max}-x_{min}$

To avoid storing individual sample values temporarily, the statistics are calculated
in a rolling fashion using [Welford's online algorithm]
(https://en.wikipedia.org/wiki/Algorithms_for_calculating_variance#Welford's_online_algorithm). 
Internally, the sum of squares of differences from the current mean 
$M_{2,n} = \sum_{i=1}^n (x_i - \bar x_n)^2$, is calculated iteratively 
via $M_{2,n} = M_{2,n-1} + (x_n - \bar x_{n-1})(x_n - \bar x_n)$.
Based on $M_{2,n}$ the variance is derived as $\sigma^2_n = \frac{M_{2,n}}{n}$.

### Sampling counter modes

At the end of the counting process, the sampling counter modes are used to specify 
which value(s) should be published (to hdf5 file and database).

The available modes can be found in `bliss.common.measurement.SamplingMode`:

```
    TEST_SESSION [1]: from bliss.common.measurement import SamplingMode
    TEST_SESSION [2]: list(SamplingMode)
             Out [3]: [<SamplingMode.MEAN: 1>,
                       <SamplingMode.STATS: 2>,
                       <SamplingMode.SAMPLES: 3>,
                       <SamplingMode.SINGLE: 4>,
                       <SamplingMode.LAST: 5>,
                       <SamplingMode.INTEGRATE: 6>]
                       <SamplingMode.INTEGRATE_STATS: 7>]
```

#### SamplingMode.MEAN

The default mode is `MEAN` which returns the mean (average) value of all 
samples, which have been read during the counting time.

![MEAN_timeline](img/sampling_timeline_MEAN.svg)

<!-- svg rendered with https://www.planttext.com
@startuml

title SamplingMode.MEAN
start

:sum=0;
repeat
  :read data from device;
  :add read value to sum;
repeat while (counting time over?)

:return sum / number of read cycles;

stop


@enduml
 -->
![MEAN_AVERAGE](img/sampling_uml_MEAN.svg)

#### SamplingMode.INTEGRATE

in addition to `SamplingMode.MEAN` the nominal counting time is taken into
account. This way a counter in the mode `SamplingMode.INTEGRATE` returns the
equivalent of the sum of all samples normalized by the counting time. 
A use case for this mode is for example the reading of a diode, that should yield
a value approximately proportional to the number of photons that hit the diode
during the counting time.


![INTEGRATE_timeline](img/sampling_timeline_INTEGRATE.svg)

#### SamplingMode.STATS

publishes all the values as calculated for the sampling counter statistics 
(see above) into the hdf5 file and the redis database.


#### SamplingMode.INTEGRATE_STATS

equivalent to `SamplingMode.STATS`, but for counters that should behave as 
described in `SamplingMode.INTEGRATE` yielding statistics in additional channels.

#### SamplingMode.SINGLE

A counter in this mode publishes only the first sample read from the device,
discarding any further samples. If possible (i.e. there is no counter in any 
other mode on the same `AquisitionDevice`) only one sample will be read.


![SINGLE_timeline](img/sampling_timeline_SINGLE.svg)

#### SamplingMode.LAST

A counter in this mode publishes only the last sample discarding any further samples.

![LAST_timeline](img/sampling_timeline_LAST.svg)

#### SamplingMode.SAMPLES

Is different from other modes in the sense, that in addition to `SamplingMode.MEAN`,
it generates an additional 1d dataset containing the individual samples in a
counting period and also publishes it. It can e.g. be used to do some more 
complex statistical analysis of the measured values or, as basis for
any `CalcCounter`, that can be used to extract derived quantities from the
original dataset. Following is an example for a CalcCounter, that returns the median:

 
```
TEST_SESSION [1]: from bliss.common.measurement import CalcCounter
             ...: from bliss.scanning.acquisition.calc import CalcHook
             ...: import numpy
             ...: class Median(CalcHook):
             ...:     def compute(self,sender,data_dict):
             ...:         if "_samples" in sender.name:
             ...:             return {"median":numpy.median(data_dict[sender.name])}
             ...: medi = CalcCounter('median',Median(),diode9)
             ...: diode9.mode = "SAMPLES"

TEST_SESSION [2]: ct(.1,medi)
         Out [2]: Scan(number=224, name=ct, path=<no saving>)
	
                  dt[s] =          0.0 (         0.0/s)
                  diode9 = 19.333333333333332 ( 193.33333333333331/s)
                  median =         -7.0 (       -70.0/s)
```

## Integrating counter

### example 1

A controller exporting N counters.



## NOTES
![Screenshot](img/counters_hierarchy.svg)

## Calculation counter

Calculation counters can be use to do some computation on raw values
of real counters.

### Expression based calc counter

Do define calculational counters directly in the *YAML* it is possible to use
`ExpressionCalcCounter` or `ExpressionCalcCounterController`. These two classes extend the Calculation Counter framework such that expressions defined in the *YAML* are evaluated during the calculation.

Here are some example configurations:

For a single counter 
```
- plugin: bliss
  module: expression_based_calc
  class: ExpressionCalcCounter
  name: simu_expr_calc
  expression: m*x+b
  inputs:
      - counter : $diode
        tags: x
      - counter : $diode2
        tags: b
  constants:
      m : 10
```

For multiple counters 
```
- plugin: bliss
  module: expression_based_calc
  class: ExpressionCalcCounterController
  name: simu_expr_calc_ctrl
  inputs:
      - counter: $simu1.counters.deadtime_det0
        tags: x
        
      - counter: $diode2
        tags: y
  constants:
       m : 10
       n : 100
  outputs:
      - name: out3
        expression:  m*x
      - name: out4 
        expression:  n*y
```


### Simple example

In this example the calculation counter will return the mean of two
real counters.
Real counters are **diode** and **diode2**.

```python
from bliss.common.measurement import CalcCounter
from bliss.scanning.acquisition.calc import CalcHook

# Mean caclulaion
class Mean(CalcHook):
    def prepare(self):
        self.data = {}
    def compute(self,sender,data_dict):
    	# Gathering all needed data to calculate the mean
	# Datas of several counters are not emitted at the same time
        nb_point_to_emit = numpy.inf
        for cnt_name in ('diode','diode2'):
            cnt_data = data_dict.get(cnt_name,[])
            data = self.data.get(cnt_name,[])
            if len(cnt_data):
                data = numpy.append(data,cnt_data)
                self.data[cnt_name]=data
            nb_point_to_emit = min(nb_point_to_emit,len(data))
	# Maybe noting to do
        if not nb_point_to_emit:
            return

        # Calculation
        mean_data = (self.data['diode'][:nb_point_to_emit] +
                     self.data['diode2'][:nb_point_to_emit]) / 2.
        # Removing already computed raw datas
        self.data = {key:data[nb_point_to_emit:]
                     for key,data in self.data.items()}
        # Return name musst be the same as the counter name:
	# **mean** in that case
        return {"mean":mean_data}

mean = CalcCounter("mean",Mean(),diode,diode2)
```



#Tutorial

Use-case examples to export new counters in BLISS.

##Sampling counters

###Simple case, a controller with only one counter

In this example the sampling counter and the controller is the same instance.
and we want to read value from a **tcp server** the emitted random values.

```bash
cat /dev/urandom | nc -k -l -p 3333
```


Bliss counter configuration may look like:

```yaml
- plugin: bliss
  package: simple_random
  class: RandomCnt
  name: rand_cnt
  tcp:
     url: localhost:3333
```

And in file **simple_random.py**:

```python
import struct
from bliss.comm.util import get_comm
from bliss.common.measurement import SamplingCounter

class RandomCnt(SamplingCounter):
    def __init__(self,name,config):
        super().__init__(name,self)
        self.comm = get_comm(config)

    def read(self):
        random_value = self.comm.read(4)
        self.comm.close()
        return struct.unpack('I',random_value)[0]
```

In bliss console:

```
BLISS [1]: rand_cnt = config.get('rand_cnt')
BLISS [2]: rand_cnt.read()
  Out [2]: 2300708583
BLISS [3]: ct(1,rand_cnt)

Mon Jul 29 19:36:49 2019
     dt[s] =          0.0 (         0.0/s)
  rand_cnt = 2136576723.7867134 ( 2136576723.7867134/s)
  Out [3]: Scan(number=3, name=ct, path=<no saving>)
```

### Severals counters sharing same controller

In this example we will export individual counters defined in the configuartion.
The counter controller read all information about the current world population with
the `.read_all` method.

In this case configuration look like:

```yaml
- plugin: bliss
  package: worldometers
  class: WorldCounter
  counters:
      - name: current_world_population
      - name: day_births
      - name: day_deaths
```

The file **worldometers.py**:

```python
from bs4 import BeautifulSoup
from urllib.request import urlopen
from bliss.common.measurement import SamplingCounter

class WorldoMeterCtrl:
    COUNTER_NAME_2_ID = {
        'current_world_population': 'cp1',
        'current_world_population_male': 'cp2',
        'current_world_population_female': 'cp3',
        'day_births' : 'cp7',
        'year_births' : 'cp6',
        'day_deaths': 'cp9',
        'year_deaths': 'cp8',
        }
    @property
    def name(self):
        return 'worldometer'
    
    def read_all(self,*counters):
        url = 'https://countrymeters.info/en/World'
        html = urlopen(url)
        soup = BeautifulSoup(html, 'html.parser')
        return [self._get_field_value(soup, self.COUNTER_NAME_2_ID[cnt.name])
                for cnt in counters]
    
    @staticmethod
    def _get_field_value(soup,name):
        return int(soup.find(id=name).getText().replace(',',''))

CONTROLLER = WorldoMeterCtrl()
    
class WorldCounter(SamplingCounter):
    def __init__(self,name,config):
        super().__init__(name,CONTROLLER)
```

!!! note
    `WorldCounter.read` use the `read_all` of the controller

In bliss console:

```
BLISS [1]: current_world_population = config.get('current_world_population')
BLISS [2]: day_births = config.get('day_births')
BLISS [3]: day_births.read()
  Out [3]: 248807
BLISS [4]: day_deaths = config.get('day_deaths')
BLISS [5]: ct(1,current_world_population,day_births,day_deaths)

Tue Jul 30 15:03:20 2019

                     dt[s] =          0.0 (         0.0/s)
  current_world_population = 7723065258.0 ( 7723065258.0/s)
                day_births =     247874.0 (    247874.0/s)
                day_deaths =      98390.0 (     98390.0/s)
  Out [5]: Scan(number=9, name=ct, path=<no saving>)

BLISS [6]: loopscan(10,.1,current_world_population,day_births,day_deaths,save=False)

Scan 10 Tue Jul 30 15:04:00 2019 <no saving> default user = seb
loopscan 10 0.1

           #         dt[s]  current_world_population    day_births    day_deaths
           0             0               7.72307e+09        248062         98464
           1      0.723097               7.72307e+09        248066         98466
           2       1.45873               7.72307e+09        248071         98468
           3       2.21063               7.72307e+09        248075         98470
           4       2.94659               7.72307e+09        248075         98470
           5       3.73903               7.72307e+09        248080         98472
           6       4.49515               7.72307e+09        248085         98473
           7       5.21481               7.72307e+09        248089         98475
           8       5.97999               7.72307e+09        248089         98475
           9       6.78664               7.72307e+09        248094         98477

Took 0:00:07.647674
  Out [6]: Scan(number=10, name=loopscan, path=<no saving>)
```

### A controller with severals counters

Here we have a controller which hold all sensor of a linux pc as a bliss SamplingCounter.
Basically we use the `sensors` linux command.

The configuration:

```yaml
- plugin: bliss
  package: linux_sensors
  class: Sensor
  name: sensor
```

The file **linux_sensors.py**

```python
import re
from gevent import subprocess
from bliss.common.measurement import SamplingCounter,counter_namespace
from bliss.common.utils import autocomplete_property

class Sensor:
    def __init__(self,name,config):
        self.name = name

    @autocomplete_property
    def counters(self):
        counters = [SamplingCounter(name,self) for name in self._read_sensors()]
        return counter_namespace(counters)
    
    def read_all(self,*counters):
        sensors_values = self._read_sensors()
        return [sensors_values[cnt.name] for cnt in counters]

    def _read_sensors(self):
        p = subprocess.Popen("sensors",stdout=subprocess.PIPE)
        exp = re.compile(b"^(.+?): *[+-]?(\d+(\.\d*)?|\.\d+)")
        name2values = dict()
        name2nb = dict()
        for line in p.stdout.readlines():
            g = exp.match(line)
            if g:
                name,value = g.group(1),g.group(2)
                name = name.decode()
                name = name.replace(' ','_')
                nb = name2nb.setdefault(name,-1) + 1
                name2nb[name] = nb
                if nb :
                    name2values[f'{name}_{nb}'] = value
                else:
                    name2values[name] = value
        return name2values
```

!!! note
    property `.counters` is used by standard scans to get counters of
    a controller.

In bliss console:

```
BLISS [1]: ls = config.get('linux_sensor')                                                                                                                                                                   
BLISS [2]: ct(1,ls)                                                                                                                                                                                          

Wed Jul 31 10:53:46 2019

          dt[s] =          0.0 (         0.0/s)
            CPU = 42.561797752808985 ( 42.561797752808985/s)
         Core_0 = 38.04494382022472 ( 38.04494382022472/s)
         Core_1 = 40.04494382022472 ( 40.04494382022472/s)
         Core_2 = 38.17977528089887 ( 38.17977528089887/s)
         Core_3 = 38.95505617977528 ( 38.95505617977528/s)
      Other_Fan =          0.0 (         0.0/s)
    Other_Fan_1 = 601.943820224719 ( 601.943820224719/s)
   Package_id_0 = 43.04494382022472 ( 43.04494382022472/s)
  Processor_Fan = 1000.0337078651686 ( 1000.0337078651686/s)
         SODIMM =          0.0 (         0.0/s)
       SODIMM_1 =         36.0 (        36.0/s)
       SODIMM_2 =         32.0 (        32.0/s)
  Out [2]: Scan(number=14, name=ct, path=<no saving>)

BLISS [3]: loopscan(5,0.1,ls,save=False)                                                                                                                                                                     

Scan 15 Wed Jul 31 10:54:59 2019 <no saving> default user = seb
loopscan 5 0.1

           #         dt[s]           CPU        Core_0        Core_1        Core_2        Core_3     Other_Fan   Other_Fan_1  Package_id_0  Processor_Fan        SODIMM      SODIMM_1      SODIMM_2
           0             0            40            36            34            39            38             0       597.286            41        1004.29             0            36            32
           1      0.102002            41            36            34            39            38             0       588.857            41           1005             0            36            32
           2      0.202884            41            36            34            39            38             0         591.5            41           1006             0            36            32
           3      0.304939            41            36            34            39            38             0         593.5            41           1007             0            36            32
           4      0.406526            41            36            34            39            38             0       595.333            41           1007             0            36            32

Took 0:00:00.576275
  Out [3]: Scan(number=15, name=loopscan, path=<no saving>)

```

#### Refinement

You want to specify in the configuration of this controller which
`default counters` are used for standard scan.  To do it you have to
provide a **property** `.counter_groups` which return a group
**default**

first you need to change your configuration file to:

```yaml
- plugin: bliss
  package: linux_sensors
  class: Sensor
  name: sensor
  default_counters: [Core_0,Core_1,Core_2,Core_3]
```

Manage the **default_counters** in the constructor of you controller

```python
    def __init__(self,name,config):
        self.name = name
        self.default_counters = [SamplingCounter(name,self)
                                 for name in config.get('default_counters',[])]
```

and add the **property** `.counter_groups`:

```python
    @autocomplete_property
    def counter_groups(self):
        if self.default_counters:
            return namespace({'default':self.default_counters})
        else:
            return namespace({})
```

!!! note
    bliss standard scan look first the **default** group in `.counter_groups` if exist.
    if not get the counters for `.counters` property. For this controller if
    the **default_counters** is not in the configuration file or empty, default scan
    will enable all counters.

Final file :

```python
import re
from gevent import subprocess
from bliss.common.measurement import SamplingCounter,counter_namespace,namespace
from bliss.common.utils import autocomplete_property

class Sensor:
    def __init__(self,name,config):
        self.name = name
        self.default_counters = [SamplingCounter(name,self)
                                 for name in config.get('default_counters',[])]
    @autocomplete_property
    def counters(self):
        counters = [SamplingCounter(name,self) for name in self._read_sensors()]
        return counter_namespace(counters)

    @autocomplete_property
    def counter_groups(self):
        if self.default_counters:
            return namespace({'default':self.default_counters})
        else:
            return namespace({})
        
    def read_all(self,*counters):
        sensors_values = self._read_sensors()
        return [sensors_values[cnt.name] for cnt in counters]

    def _read_sensors(self):
        p = subprocess.Popen("sensors",stdout=subprocess.PIPE)
        exp = re.compile(b"^(.+?): *[+-]?(\d+(\.\d*)?|\.\d+)")
        name2values = dict()
        name2nb = dict()
        for line in p.stdout.readlines():
            g = exp.match(line)
            if g:
                name,value = g.group(1),g.group(2)
                name = name.decode()
                name = name.replace(' ','_')
                nb = name2nb.setdefault(name,-1) + 1
                name2nb[name] = nb
                if nb :
                    name2values[f'{name}_{nb}'] = value
                else:
                    name2values[name] = value
        return name2values
```

In bliss console:

```
BLISS [1]: ls = config.get('linux_sensor')
BLISS [2]: ct(1,ls)

Wed Jul 31 14:20:03 2019

   dt[s] =          0.0 (         0.0/s)
  Core_0 =         36.0 (        36.0/s)
  Core_1 =         33.0 (        33.0/s)
  Core_2 =         41.0 (        41.0/s)
  Core_3 =         33.0 (        33.0/s)
  Out [2]: Scan(number=22, name=ct, path=<no saving>)

BLISS [3]: loopscan(5,.1,ls,save=False)

Scan 23 Wed Jul 31 14:20:21 2019 <no saving> default user = seb
loopscan 5 0.1

           #         dt[s]        Core_0        Core_1        Core_2        Core_3
           0             0            36            32            40            35
           1      0.101498            36            32            40            35
           2      0.203017            36            32            40            35
           3      0.304585            36            32            40            35
           4       0.40642            36            32            40            35

Took 0:00:00.541600
  Out [3]: Scan(number=23, name=loopscan, path=<no saving>)

BLISS [4]: loopscan(5,.1,ls.counters,save=False)

Scan 24 Wed Jul 31 14:20:30 2019 <no saving> default user = seb
loopscan 5 0.1

           #         dt[s]           CPU        Core_0        Core_1        Core_2        Core_3     Other_Fan   Other_Fan_1  Package_id_0  Processor_Fan        SODIMM      SODIMM_1      SODIMM_2
           0             0            39            36            33            36            34             0           587            40         998.75             0            35            32
           1      0.100959            39            36            33            36            34             0        586.75            40        999.625             0            35            32
           2       0.20197            40            36            33            36            34             0           586            40         1001.5             0            35            32
           3      0.303091            40            36            33            36            34             0       586.333            40        1003.11             0            35            32
           4      0.412361            40            36            33            36            34             0        587.75            40        1004.12             0            35            32

Took 0:00:00.576561
  Out [4]: Scan(number=24, name=loopscan, path=<no saving>)
```

##Raw Counters

Here is an example when you cannot use the counter type defined in bliss
core (**sampling counter**,**integrating counter**).

In this example the controller read the realtime *currency conversion*
and export is special counters, one per *currency conversion*.  Then
for standard scan each `counter` create two `AcquisitionChannel` one
**bid** and one **ask**

Configuration:

```yaml
- plugin: bliss
  package: currency
  class: Currency
  name: curr
```

python code:

```python
import requests
import json
import weakref
import numpy

from bliss.common.utils import autocomplete_property
from bliss.common.measurement import BaseCounter, namespace, counter_namespace
from bliss.scanning.chain import AcquisitionSlave, AcquisitionChannel


class Currency:
    def __init__(self,name,config):
        self.__name = name
        self.default_counters = [Counter(self,name)
                                 for name in config.get('default_counters',[])]
    @property
    def name(self):
        return self.__name

    @autocomplete_property
    def counters(self):
        return counter_namespace(Counter(self,name) for name in self.update().keys())

    @autocomplete_property
    def counter_groups(self):
        groups = {}
        if self.default_counters:
            groups['default'] = self.default_counters
        return namespace(groups)

    def update(self):
        r = requests.request(url="https://financialmodelingprep.com/api/v3/forex",method="GET")
        data = json.loads(r.content)
        return {conversion.pop('ticker').replace('/','_') : conversion
                for conversion in data['forexList']}


class Counter(BaseCounter):
    def __init__(self,financial,counter_name):
        self._controller = weakref.ref(financial)
        self._name = counter_name
    @autocomplete_property
    def controller(self):
        return self._controller()
    @property
    def name(self):
        return self._name
    
    def create_acquisition_device(self,scan_pars,**settings):
        return AcqDevice(self.controller,**scan_pars)

class AcqDevice(AcquisitionSlave):
    def __init__(self,financial,**scan_pars):
        AcquisitionSlave.__init__(self,financial,financial.name,
                                   npoints = scan_pars.get('npoints',1),
                                   prepare_once=True)
        self.counters = list()
        
    def add_counter(self, counter):
        channels = [AcquisitionChannel(self, f'{counter.name}:{k}', numpy.float, ())
                    for k in ['bid','ask']]
        self.channels.extend(channels)
        self.counters.append(counter)

    def prepare(self):
        pass

    def start(self):
        pass

    def trigger(self):
        values = self.device.update()
        values_dict = dict()
        for counter in self.counters:
            for k in ['bid','ask']:
                values_dict[f'{counter.name}:{k}'] = values[counter.name][k]
        self.channels.update(values_dict)

    def stop(self):
        pass
```
