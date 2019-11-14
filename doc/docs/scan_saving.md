
## Architecture

![Screenshot](img/scan_data_flow_path.svg)

## SCAN_SAVING

`SCAN_SAVING` is a per session structure to tell BLISS how to save data.

Access it with `.scan_saving` property of Session object.

From Bliss Shell you have also access to a global variable `SCAN_SAVING` that refers to `current_session.scan_saving`.

example:

```
BLISS [1]: SCAN_SAVING
Parameters (default)
  .base_path            = '/tmp/scans'
  .date                 = '20181121'
  .date_format          = '%Y%m%d'
  .device               = '<images_* only> acquisition device name'
  .images_path_relative = True
  .images_path_template = '{scan}'
  .images_prefix        = '{device}_'
  .scan                 = '<images_* only> scan node name'
  .session              = 'default'
  .template             = '{session}/'
  .user_name            = 'obi-wan'
  .writer               = 'hdf5'
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
    - `parent`: parent node for publishing data via Redis
    - `writer`: Data file writer object.

!!! note
    As the ScanSaving object corresponds to a persistent
    structure in Redis, functions as key values will be
    serialized. Make sure the functions are serializable.

#### SCAN_SAVING writer

`.writer` is a special member of `SCAN_SAVING`; it indicates which
writer to use for saving data. BLISS only supports the HDF5 file
format for scan data, although more writers could be added to the
project later.

### Configuration example

#### template configuration example

In this example `SCAN_SAVING` we will add two extra parameters
(**sample** and **experiment**) and use them to generate the final path.

```python
TEST_SESSION [1]: # Set the base path to /data/visitor
TEST_SESSION [2]: SCAN_SAVING.base_path = '/data/visitor'
TEST_SESSION [3]: #Adding the two new parameters
TEST_SESSION [4]: SCAN_SAVING.add('sample','lysozyme')
TEST_SESSION [5]: SCAN_SAVING.add('experiment','mx1921')
TEST_SESSION [6]: # Use them in the template
TEST_SESSION [7]: SCAN_SAVING.template = '{experiment}/{sample}'
TEST_SESSION [8]: SCAN_SAVING
         Out [8]: Parameters (default) - 

                     .base_path            = '/data/visitor'
                     .data_filename        = 'data'
                     .date                 = '20190403'
                     .date_format          = '%Y%m%d'
                     .experiment           = 'mx1921'
                     .images_path_relative = True
                     .images_path_template = 'scan{scan_number}'
                     .images_prefix        = '{img_acq_device}_'
                     .img_acq_device       = '<images_* only> acquisition device name'
                     .sample               = 'lysozyme'
                     .scan_name            = 'scan name'
                     .scan_number          = 'scan number'
                     .scan_number_format   = '%04d'
                     .session              = 'test_session'
                     .template             = '{experiment}/{sample}'
                     .user_name            = 'seb'
                     .writer               = 'hdf5'
TEST_SESSION [9]: SCAN_SAVING.get_path()
         Out [9]: '/data/visitor/mx1921/lysozyme'
```

In a case the experiment can be get automatically, **experiment** can be set as a function:

```python
TEST_SESSION [10]: def get_experiment(scan_saving): 
              ...:     if scan_saving.user_name == 'seb': 
              ...:        return 'mx1921' 
              ...:     else: 
              ...:        return 'unknown'
	      
TEST_SESSION [11]: SCAN_SAVING.add('experiment',get_experiment)
TEST_SESSION [12]: SCAN_SAVING.get_path()
         Out [12]: '/data/visitor/mx1921/lysozyme'
	 
TEST_SESSION [13]: SCAN_SAVING.user_name='toto'
TEST_SESSION [14]: SCAN_SAVING.get_path()
         Out [14]: '/data/visitor/unknown/lysozyme'
```
