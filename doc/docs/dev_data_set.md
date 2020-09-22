## Dataset handling in bliss (according to ESRF Datapolicy)

in Bliss icat datasets are represented as `dataset` objects that
can be accessed (for debugging) via `SCAN_SAVING.dataset_object`.
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
DEMO_SESSION [15]: SCAN_SAVING.dataset_object.add_technique(definitions.techniques.FLUO)

``` 

actually adding metadata can be done like this:

```python
scan_saving.dataset_object.write_metadata_field("FLUO_i0", str(17.1))
```

please note that icat only accepts strings as metadata values.

once metadata is added it is possible to check which fields are still missing
in the dataset to have a full set of metadata:

```python
DEMO_SESSION [16]: SCAN_SAVING.dataset_object.missing_technique_fields
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
    scan_saving = ScanSaving("my_custom_scansaving")

    # create a new dataset ony for the scans in here.
    scan_saving.newdataset("my_new_dataset")

    definitions = Definitions()

    scan_saving.dataset_object.add_technique(definitions.techniques.FLUO)

    # just prepare a custom scan ...
    ls = loopscan(3, .1, diode1, run=False)
    s = Scan(ls.acq_chain, scan_saving=scan_saving)

    # add some metadata before the scan runs
    scan_saving.dataset_object.write_metadata_field("FLUO_i0", str(17.1))

    # run the scan[s]
    s.run()

    # add some metadata after the scan runs
    scan_saving.dataset_object.write_metadata_field("FLUO_it", str(18.2))

    # close the dataset
    scan_saving.enddataset()

```

## check already collected metadata
to check already collected metatdata use `get_current_icat_metadata`

```
DEMO_SESSION [2]: SCAN_SAVING.dataset_object.get_current_icat_metadata()
         Out [2]: {'InstrumentVariables_name': 'sy sz ', 'InstrumentVariables_value': '0.0 0.0 ', 'InstrumentSlitSecondary_vertical_gap': '0.0', 'InstrumentSlitSecondary_vertical_offset': '0.0', 'SamplePositioners_name': 'sy sz', 'SamplePositioners_value': '0.0 0.0'}
```

## redis stream to receive events on datasets of a session
there is a demo in `bliss.git/bliss/icat/demo_listener.py`. This part of the 
implementation of datasest is still experimental (not used for publishing
to icat) may change. 
