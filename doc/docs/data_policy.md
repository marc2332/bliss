A data policy determines data structure (file format and directory structure) and registeration of data collection with external services. BLISS comes with two data policies

1. The [ESRF data policy](#esrf-data-policy) which allows users to access their data and electronic logbook at https://data.esrf.fr. The data is written in [Nexus compliant](https://www.nexusformat.org/) HDF5 files in a specific directory structure. 

!!! note
    Read more about [configuring ESRF data policy](installation_esrf.md#ESRF data policy)

2. The [basic data policy](#basic-data-policy) does not impose a data directory structure or register data with any external service. Data can (but does not have to be) written in [Nexus compliant](https://www.nexusformat.org/) HDF5 files. The basic data policy is the default policy for BLISS.

## ESRF data policy

This data policy requires the user to specify *proposal*, *sample* and *dataset*. This will completely define how data is organized.

### Change proposal

```
DEMO  [1]: newproposal("blc123")
Proposal set to 'blc123`
Data path: /data/id00/inhouse/blc123/id00/sample/sample_0001
```
When no proposal name is given, the default proposal is inhouse proposal `{beamline}{yymm}`. For example at ID21 in January 2020 the default proposal name is `id212001`.

The data root directory is derived from the proposal name

* no name given: `/data/{beamline}/inhouse/`
* *ih** and *blc**: `/data/{beamline}/inhouse/`
* *test**, *tmp** or *temp**: `/data/{beamline}/tmp/`
* all other names: `/data/visitor/`

These root path can be [configured](installation_esrf.md#ESRF data policy) but these are the defaults.

### Change sample

```
DEMO  [2]: newsample("sample1")
Sample set to 'sample1`
Data path: /data/id00/inhouse/blc123/id00/sample1/sample1_0001
```

When no sample name is given, the default sample name "sample" is used. Note that you can always come back to an existing sample.

### Change dataset

#### Named datasets

```
DEMO  [3]: newdataset("area1")
Dataset set to 'area1`
Data path: /data/id00/inhouse/blc123/id00/sample1/sample1_area1
```

When the dataset already exists the name will be automatically incremented ("area1_0002", "area1_0003", ...). Note that you can never come back to the same dataset after you changed dataset.

#### Unnamed datasets

```
DEMO  [4]: newdataset()
Dataset set to '0002`
Data path: /data/id00/inhouse/blc123/id00/sample1/sample1_0002
```

The dataset will be named automatically "0001", "0002", ... The dataset number is independent for each sample. Note that you can never come back to the same dataset after you changed dataset.

### Policy state

To get an overview of the current state of the data policy

```
DEMO  [5]: SCAN_SAVING
  Out [5]: Parameters (default) - 
            
              .user_name             = 'denolf'
              .images_path_template  = 'scan{scan_number}'
              .images_prefix         = '{img_acq_device}_'
              .date_format           = '%Y%m%d'
              .scan_number_format    = '%04d'
              .dataset_number_format = '%04d'
              .technique             = ''
              .session               = 'demo'
              .date                  = '20200208'
              .scan_name             = '{scan_name}'
              .scan_number           = '{scan_number}'
              .img_acq_device        = '<images_* only> acquisition device name'
              .writer                = 'nexus'
              .data_policy           = 'ESRF'
              .template              = '{proposal}/{beamline}/{sample}/{sample}_{dataset}'
              .beamline              = 'id00'
              .proposal              = 'blc123'
              .proposal_type         = 'inhouse'
              .base_path             = '/data/id00/inhouse'
              .sample                = 'sample1'
              .dataset               = '0001'
              .data_filename         = '{sample}_{dataset}'
              .images_path_relative  = True
              .creation_date         = '2020-02-08-12:09'
              .last_accessed         = '2020-02-08-12:12'
            --------------  ---------  -------------------------------------------------------------------
            exists          filename   /data/id00/inhouse/blc123/id00/sample1/sample1_0001/sample1_0001.h5
            exists          directory  /data/id00/inhouse/blc123/id00/sample1/sample1_0001
            Metadata        RUNNING    Dataset is running
            --------------  ---------  -------------------------------------------------------------------
```

#### MetadataManager state

The state of the MetadataManager device can be

 * OFF: No experiment ongoing
 * STANDBY: Experiment started, sample or dataset not specified
 * ON: No dataset running
 * RUNNING: Dataset is running
 * FAULT: Device is not functioning correctly

Every time a scan is started, BLISS verifies that the dataset as specified in the session's `SCAN_SAVING` object is *RUNNING*. If this is not the case, BLISS will close the previous running dataset (if any) and start the new dataset.

## Basic data policy

This data policy requires the user to use the [`SCAN_SAVING`](dev_data_policy_basic.md#scan_saving) object directly to define where the data will be saved. The data location is completely determined by specifying *base_path*, *template*, *data_filename* and *writer*

```
DEMO  [1]: SCAN_SAVING.base_path = "/tmp/data"
DEMO  [2]: SCAN_SAVING.writer = "nexus"
DEMO  [3]: SCAN_SAVING.template = "{date}/{session}/{mysubdir}"
DEMO  [4]: SCAN_SAVING.date_format = "%y%b"
DEMO  [5]: SCAN_SAVING.add("mysubdir", "sample1")
DEMO  [6]: SCAN_SAVING.data_filename = "scan{scan_number}"
DEMO  [7]: SCAN_SAVING.filename
  Out [7]: '/tmp/data/20Feb/demo/sample1/scan{scan_number}.h5'
```

Note that each attribute can be a template string to be filled with other attributes from the [`SCAN_SAVING`](dev_data_policy_basic.md#scan_saving) object.

### Policy state

To get an overview of the current state of the data policy

```
DEMO [8]: SCAN_SAVING
 Out [8]: Parameters (default) - 
         
         .base_path            = '/tmp/data'
         .data_filename        = 'scan{scan_number}'
         .user_name            = 'denolf'
         .template             = '{date}/{session}/{mysubdir}'
         .images_path_relative = True
         .images_path_template = 'scan{scan_number}'
         .images_prefix        = '{img_acq_device}_'
         .date_format          = '%y%b'
         .scan_number_format   = '%04d'
         .mysubdir             = 'sample1'
         .session              = 'demo'
         .date                 = '20Feb'
         .scan_name            = '{scan_name}'
         .scan_number          = '{scan_number}'
         .img_acq_device       = '<images_* only> acquisition device name'
         .writer               = 'nexus'
         .data_policy          = 'None'
         .creation_date        = '2020-02-08-12:04'
         .last_accessed        = '2020-02-08-12:05'
         --------------  ---------  -----------------------------------------------------------------
         exists          filename   /tmp/data/20Feb/demo/sample1/scan{scan_number}.h5
         exists          directory  /tmp/data/20Feb/demo/sample1
         --------------  ---------  -----------------------------------------------------------------
```
