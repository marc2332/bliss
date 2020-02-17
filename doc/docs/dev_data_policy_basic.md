# Basic data policy

This policy is meant for testing only. It does not enforce data structure (file format)

## Summary

To enable the basic data policy

1. Install and run the [Nexus writer](dev_data_nexus_server.md) to write the data in Nexus format (optional)

2. Specify file directory and name using the [SCAN_SAVING](#scan_saving) object in the BLISS session

## SCAN_SAVING

`SCAN_SAVING` is a per session structure to tell BLISS how to save data.

Access it with `.scan_saving` property of Session object.

From Bliss Shell you have also access to a global variable `SCAN_SAVING` that
refers to `current_session.scan_saving`.

example:

```
DEMO  [1]: SCAN_SAVING
  Out [1]: Parameters (default) -

             .base_path            = '/tmp/toto/'
             .data_filename        = 'data'
             .user_name            = 'guilloud'
             .template             = '{session}/'
             .images_path_relative = True
             .images_path_template = 'scan{scan_number}'
             .images_prefix        = '{img_acq_device}_'
             .date_format          = '%Y%m%d'
             .scan_number_format   = '%04d'
             .session              = 'cyril'
             .date                 = '20190926'
             .scan_name            = 'scan name'
             .scan_number          = 'scan number'
             .img_acq_device       = '<images_* only> acquisition device name'
             .writer               = 'hdf5'
             .creation_date        = '2019-08-23-10:08'
             .last_accessed        = '2019-09-26-16:09'
           --------------  ---------  -----------------------
           does not exist  filename   /tmp/toto/cyril/data.h5
           exists          root_path  /tmp/toto/cyril/
           --------------  ---------  -----------------------
```

`base_path` corresponds to the top-level directory where scans are
stored. Then, `template` completes the path. It uses Python's string
interpolation syntax to specify how to build the file path from key
values. Keys can be freely added. Key values can be numbers or
strings, or functions. In case of function key values, the function
return value is used.

`SCAN_SAVING.get()` performs template string interpolation and returns
a dictionary, whose key `root_path` is the final path to scan files.

#### SCAN_SAVING members

* `base_path`: the highest level directory for the file path, e.g. `/data`
* `user_name`: the current Unix user name
* `session`: current BLISS session name
* `template`: defaults to `{session}/`
* `.add(key, value)`: add a new key (string) to the SCAN_SAVING structure
    - value can be a scalar or a function
* `.get_path()`: returns the build directory path where the *data file* will be saved.
* `.get()`: evaluates template ; produces a dictionary with 5 keys
    - `root_path`: `base_path` + interpolated template
    - `data_path`: fullpath for the *data file* without the extension.
    - `images_path`: path where image device should save (Lima)
    - `db_path_items`: used to create parent node for publishing data via Redis
    - `writer`: Data file writer object.

!!! note
    As the ScanSaving object corresponds to a persistent
    structure in Redis, functions as key values will be
    serialized. Make sure the functions are serializable.

#### SCAN_SAVING writer

`.writer` is a special member of `SCAN_SAVING`; it indicates which
writer to use for saving data. BLISS supports `"hdf5"` (internal writer in BLISS), `"nexus"` (the [Nexus writer](dev_data_nexus_server.md)) and `"null"` (writing disabled).

### Configuration example

#### template configuration example

In this example `SCAN_SAVING` we will add two extra parameters
(**sample** and **experiment**) and use them to generate the final path.

```python
DEMO [1]: # Set the base path to /data/visitor:
DEMO [2]: SCAN_SAVING.base_path = '/data/visitor'

DEMO [3]: # Add the two new parameters:
DEMO [4]: SCAN_SAVING.add('sample','lysozyme')
DEMO [5]: SCAN_SAVING.add('experiment','mx1921')

DEMO [6]: # Use them in the template:
DEMO [7]: SCAN_SAVING.template = '{experiment}/{sample}'

DEMO [8]: # result:
DEMO [8]: SCAN_SAVING
 Out [8]: Parameters (default) -

             .base_path            = '/data/visitor''
             .data_filename        = 'data'
             .user_name            = 'guilloud'
             .template             = '{experiment}/{sample}'
             .images_path_relative = True
             .images_path_template = 'scan{scan_number}'
             .images_prefix        = '{img_acq_device}_'
             .date_format          = '%Y%m%d'
             .scan_number_format   = '%04d'
             .experiment           = 'mx1921'
             .session              = 'cyril'
             .date                 = '20190926'
             .scan_name            = 'scan name'
             .scan_number          = 'scan number'
             .img_acq_device       = '<images_* only> acquisition device name'
             .sample               = 'lysozyme'
             .writer               = 'hdf5'
             .creation_date        = '2019-08-23-10:08'
             .last_accessed        = '2019-09-26-16:09'
            --------------  ---------  -------------------------------------
            does not exist  filename   /data/visitor/mx1921/lysozyme/data.h5
            exists          root_path  /data/visitor/mx1921/lysozyme
            --------------  ---------  -------------------------------------
DEMO [9]: SCAN_SAVING.get_path()
 Out [9]: '/data/visitor/mx1921/lysozyme'
```

In a case the experiment can be get automatically, **experiment** can be set as
a function:

```python
DEMO [10]: def get_experiment(scan_saving):
              ...:     if scan_saving.user_name == 'seb':
              ...:        return 'mx1921'
              ...:     else:
              ...:        return 'unknown'

DEMO [11]: SCAN_SAVING.add('experiment',get_experiment)
DEMO [12]: SCAN_SAVING.get_path()
 Out [12]: '/data/visitor/mx1921/lysozyme'

DEMO [13]: SCAN_SAVING.user_name='toto'
DEMO [14]: SCAN_SAVING.get_path()
 Out [14]: '/data/visitor/unknown/lysozyme'
```
