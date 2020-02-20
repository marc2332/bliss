#Data flow

In Bliss, *Data* and *Meta-data* flow from detector to
[Redis](https://redis.io) data base, they are never kept locally in
memory.  During a `Scan`, every *Data* produced by detector included
in a `Scan` will follow this rule.  *Data* are kept for a maximum of 1
day (by default and for a maximum amount of 1GB.  In any case the rule
of this data base is not to **store** *Data* but to **publish** live
*Data* to external process like *on-line data analysis*, *final
storage*...

Online data structure is detailed
[Here](data_structure.md#online-data-analysis)

![image](img/scan_data_flow_path.svg)

##Data Client(s)

It's now possible to link **On-line data analysis** easily with
a Bliss session.

Any client can subscribe to receive *Data* notification of a
`session`.  As soon as it can reach a beam-line `Beacon` server.

Already several client use this mechanism: `Flint`, `External Writer`
and [PyMca](http://pymca.sourceforge.net/)

###Simple example

`Bliss` provide a [Python](https://www.python.org) module to archive
*Data* subscription.  The following example listen to a session called
*demo_session* and follow the scan activity:

```python
from bliss.data import node

session_node = node.get_session_node('demo_session')
for event,*values in session_node.iterator.walk_on_new_events(filter='scan'):
    if event == event.NEW_NODE:
        scan = values[0]
        print(f'Scan {scan.db_name} started')
    elif event == event.END_SCAN:
        scan = values[0]
        print(f'Scan {scan.db_name} ends')
```

##Future

In near future, it would be even possible to change scanning strategy
with the computation result of an **one-line data analysis** program.
i.e: change the position range of scanning motor *during* the scan...

###Simple data-analysis interaction

Just a simple example to demonstrate the possible communication
between on-line data and a alignment scan.

In the following example, **one-line data analysis** program stop
the alignment when it estimate that enough points is taken.

```python
from bliss.config import channels
from bliss.data import node

max_value = 0.
# communcation channel for bliss session
stop_alignment = channels.Channel('stop_alignment',default_value=False)
session_node = node.get_session_node('demo_session')
for event,*values in session_node.iterator.walk_on_new_events():
    if event == event.NEW_NODE:
        node = values[0]
        if node.type == 'scan':
	    # reset max_value to 0
	    # when a new scan starts.
            max_value = 0.
    elif event == event.NEW_DATA_IN_CHANNEL:
        channel = values[0]
        if not channel.name.find('gauss') > -1:
            continue
        data_value = channel.get(-1) # last value
        if data_value > max_value:
            max_value = data_value
        elif data_value < (max_value/2.):
            print(f"Stop Alignment scan max_value:{max_value} current_value:{data_value}")
            #stop the scan
            stop_alignment.value = True
```

A simple hook to stop the scan:

```python
from bliss.config import channels
from bliss.scanning import scan

class StopAlignmentHook(scan.WatchdogCallback):
    def __init__(self):
        super().__init__()
        self._stop_flag = channels.Channel('stop_alignment',
                                           value=False)
    def on_scan_data(self,*args):
        if self._stop_flag.value:
            raise StopIteration
```

####Run it

Start the simple **on-line data analysis** program.

Then run the scan has follow:

```bash
DEMO_SESSION [1]: s = ascan(robz,-5,5,500,.001,sim_ct_gauss_noise,save=False,run=False)
DEMO_SESSION [2]: s.set_watchdog_callback(StopAlignmentHook())
DEMO_SESSION [3]: s.run()
```
