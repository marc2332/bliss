


## Architecture

![Screenshot](img/scan_data_flow_path.svg)



## SCAN_SAVING

`SCAN_SAVING` is a global structure to tell BLISS how to save data:

* where
* whith which name

example:

    BLISS [1]: print SCAN_SAVING
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
* `.get()`: evaluates template ; produces a dictionary with 2 keys
    - `root_path`: `base_path` + interpolated template
    - `parent`: parent node for publishing data via Redis

    !!! note
        As the ScanSaving object corresponds to a persistent
        structure in Redis, functions as key values will be
        serialized. Make sure the functions are serializable.

#### SCAN_SAVING writer

`.writer` is a special member of `SCAN_SAVING`; it indicates which
writer to use for saving data. BLISS only supports the HDF5 file
format for scan data, although more writers could be added to the
project later.
