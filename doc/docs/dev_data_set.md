## Dataset handling in bliss (according to ESRF Datapolicy)

in Bliss icat datasets are represented as `dataset` objects that
can be accessed (for debugging) via `SCAN_SAVING.dataset`.
These objects map to a group of scans in redis and also collect the
associated icat metadata.

## ICAT definitons
to have access to the icat fields that are defined by [DAU in hdf5_cfg.xml](https://gitlab.esrf.fr/icat/hdf5-master-config/-/blob/master/hdf5_cfg.xml)
use the provided icat definition object

```python
DEMO_SESSION [2]: from bliss.icat.definitions import Definitions
DEMO_SESSION [3]: definitions = Definitions()

DEMO_SESSION [5]: definitions.all
         Out [5]: ('MX_fluxEnd', 'InstrumentXraylens09_lens_thickness', ...)

```

there are several categories

```python

DEMO_SESSION [15]: definitions.
                                all             positioners
                                instrumentation sample
                                notes           techniques

DEMO_SESSION [8]: definitions.sample
         Out [8]: <Sample:{'SampleEnvironmentSensors_name', 'SampleEnvironment_name', ...}
```

### Technique related fields in ICAT

Currently the follwoing techniques are defined in nexus:

```python
DEMO_SESSION [12]: definitions.techniques.
                                           count  HOLO   MX     TOMO
                                           EM     index  PTYCHO WAXS
                                           FLUO   MRT    SAXS


DEMO_SESSION [13]: definitions.techniques._fields
         Out [13]: ('SAXS', 'MX', 'EM', 'PTYCHO', 'FLUO', 'TOMO', 'MRT', 'HOLO', 'WAXS')

DEMO_SESSION [14]: definitions.techniques.FLUO
         Out [14]: <FLUO:{'FLUO_scanDim1',  'FLUO_scanRange2', 'FLUO_it', ...}
``` 

To add a specific technique to a dataset object use `add_technique`
         
```python
DEMO_SESSION [15]: SCAN_SAVING.dataset.add_technique(definitions.techniques.FLUO)

``` 

actually adding metadata can be in two ways, either like this:

```python
scan_saving.dataset["FLUO_i0"] =  str(17.1)
```

or through namespaces that are intended for commandline usage:
```python
DEMO_SESSION [ 8]: SCAN_SAVING.dataset.expected.FLUO_i0 = str(17.1)

DEMO_SESSION [ 9]: SCAN_SAVING.dataset.existing

DEMO_SESSION [10]: SCAN_SAVING.dataset.all
```
Please note that icat only accepts strings as metadata values.

The `expected` namespace contains all fields that are used by the concerned techniques 
(that are added to that dataset). The `existing` namespace contains all fields that are sofar published
and `all` contains all accepted icat keys.

Once metadata is added it is possible to check which fields are still missing
in the dataset to have a full set of metadata:

```python
DEMO_SESSION [16]: SCAN_SAVING.dataset.missing_technique_fields
         Out [16]: {'FLUO_scanDim1', 'TOMO_it_end', 'FLUO_scanRange2',...}
```

Positioners and Instrument related fields can be [filled automatically](dev_icat.md).

## Custom datasets for procedures
There is an example in `bliss.git/bliss/icat/demo.py` that will be discussed here. 
In this example an isolated dataset for a dedicated experimental procedure is created 
by using a custom `ScanSaving` object. This makes sense e.g. when adding technique 
related metadata (`FLUO` definition in this case).

```python
from bliss.common.scans import loopscan
from bliss.setup_globals import diode1
from bliss.scanning.scan_saving import ScanSaving
from bliss import current_session
from bliss.scanning.scan import Scan
from bliss.icat.definitions import Definitions
from pprint import pprint


def demo_with_technique():
    """ a demo procedure using a custom scan saving"""

    scan_saving = ScanSaving("my_custom_scansaving")

    # how is it suppsed to work with the dataset name?
    ds_name = current_session.scan_saving.dataset
    ds_name += "_b"

    # create a new dataset ony for the scans in here.
    scan_saving.newdataset(ds_name)

    definitions = Definitions()

    scan_saving.dataset.add_technique(definitions.techniques.FLUO)

    # just prepare a custom scan ...
    ls = loopscan(3, .1, diode1, run=False)
    s = Scan(ls.acq_chain, scan_saving=scan_saving)

    # add some metadata before the scan runs
    scan_saving.dataset["FLUO_i0"] = str(17.1)

    # run the scan[s]
    s.run()

    # add some metadata after the scan runs
    scan_saving.dataset["FLUO_it"] = str(18.2)

    # just for the debug print at the end
    node = scan_saving.dataset.node

    # should this print be obligatory?
    scan_saving.dataset.check_metadata_consistency()

    # close the dataset
    scan_saving.enddataset()
```

## check already collected metadata
to check already collected metatdata use `get_current_icat_metadata`

```
DEMO_SESSION [2]: SCAN_SAVING.dataset.get_current_icat_metadata()
         Out [2]: {'InstrumentVariables_name': 'sy sz ', 'InstrumentVariables_value': '0.0 0.0 ', 'InstrumentSlitSecondary_vertical_gap': '0.0', 'InstrumentSlitSecondary_vertical_offset': '0.0', 'SamplePositioners_name': 'sy sz', 'SamplePositioners_value': '0.0 0.0'}
```

for commandline usage there is also the namespace `.existing` that can be used

```
DEMO_SESSION [10]: SCAN_SAVING.dataset.existing
         Out [10]: Namespace containing:
                   .InstrumentVariables_name     ('sy sz ')
                   .InstrumentVariables_value     ('0.0 0.0 ')
                   .InstrumentSlitSecondary_vertical_gap     ('0.0')
                   .InstrumentSlitSecondary_vertical_offset     ('0.0')
                   .SamplePositioners_name     ('sy sz')
                   .SamplePositioners_value     ('0.0 0.0')
                   .FLUO_i0     ('17.1')
```

## Receive events on datasets of a session through redis
there is a demo in `bliss.git/bliss/icat/demo_listener.py`.
