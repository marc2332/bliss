# NeXus compliant external writer
The code of this external NeXus writer is maintained by the ESRF Data Analysis Unit (DAU) to ensure seamless integration with data analysis tools provided by the DAU.

## External Nexus writer as a Tango device

The data writing of one BLISS session is handled by one nexus writer TANGO device.

### Register session writer with the Tango database

To register the TANGO device automatically, specify its properties in the beamline configuration files

```yaml
server: NexusWriter
personal_name: nexuswriters
device:
- tango_name: id00/bliss_nxwriter/test_session
  class: NexusWriter
  properties:
    session: test_session
```

The device class should always be __NexusWriter__ and the __session__ property should be the BLISS session name. If you want to register the device manually with the TANGO database, you can use a helper function to avoid mistakes (correct class name and session property, only one TANGO device per session)

```bash
   $ python -m nexus_writer_service.nexus_register_writer test_session --domain id00 --instance nexuswriters
```

In this example we registered a writer for BLISS session __test_session__ which runs under domain __id00__ in TANGO server instance __nexuswriters__. By default the device family is __bliss_nxwriter__ and the device name is equal to the session name. Running multiple session writers in on TANGO server instance (i.e. one process) is allowed but not recommended if the associated BLISS sessions may produce lots of data simultaneously.

### Start the Tango server

A nexus writer TANGO server (which may serve different BLISS session) can be started inside the BLISS conda environment as follows

```bash
   $ NexusWriterService nexuswriters --log=info
```

You need to specify the instance name of the TANGO server, so __nexuswriters__ in the example.

### Enable in BLISS

Select the external writer in the BLISS session in order to be notified of errors and register metadata generators

```python
SCAN_SCAVING.writer = "nexus"
```

BLISS will discover the external writer automatically. Note that if you disable the writer but have the TANGO server running, data will be saved but the BLISS session is unaware of it.


### Session writer status

The status of the TANGO device serving a BLISS session can be

 * INIT: initializing (not accepting scans)
 * ON: accepting scans (without active scan writers)
 * RUNNING: accepting scans (with active scan writers)
 * OFF: not accepting scans
 * FAULT: not accepting scans due to exception

When the server stays in the INIT state you can try calling the TANGO devices's "init" method. This can happen when the connection to beacon fails in the initialization stage. When in the OFF state, use the TANGO devices's "start" method. To stop accepting new scans, use the TANGO devices's "stop" method.

### Scan writer status

Each session writer launches a separate scan writer which saves the data of a particular scan (subscans are handled by the same scan writer). The scan writer status can be

 * INIT: initializing (not accepting data yet)
 * ON: accepting data
 * OFF: not accepting data (scan is done and all data has been saved)
 * FAULT: not accepting data due to exception

The final state will always be OFF (finished succesfully) or FAULT (finished unsuccesfully). The session purges the scan writers that are finished after 5 minutes. The state of those scans (which reflects whether the data has been written succesfully or not) is lost forever.

When the state is ON while the scan is finished, the writer did not received the "END_SCAN" event. You can stop the writer with the TANGO devices's "stop_scan" method. This gracefully finalizes the writing. As a last resort you can invoke the "kill_scan" method which might result in incomplete or even corrupt data (when it is executing a write operation while you kill it).

### Concurrent writing

Scans run in parallel and multi-to-master scans will cause the writer to create and modify multiple NXentry groups in the same HDF5 file concurrently.

To protect against multiple writers listening to the same session (and therefore writing the same data) BLISS verifies whether only one writer is listening to the current BLISS session before starting a scan. If multiple writers are active nevertheless, each writer checks whether the NXentry exists before trying to create it at the start of the scan. If it exists, the writer goes in the FAULT state and it will not try to write the data of the (sub)scan associated with this NXentry. This checking relies on "h5py.File.create_group" which is not an atomic operation so not bulletproof.

### Concurrent reading

Each scan writer holds the HDF5 file open in append mode for the duration of the scan. HDF5 file locking is disabled. Flushing is done regularly so readers can see the latest changes.

!!! warning
    A reader should never open the HDF5 file in append mode. Even when only performing read operation, this will result in a corrupted file!

### File permissions

The HDF5 file and parent directories are created by the TANGO server and are therefore owned by the user under which the server process is running. Subdirectories are created by the BLISS session (e.g. directories for lima data) and are therefore owned by the user under which the BLISS session is running. Files in those subdirectories are created by the device servers and are therefore owned by their associated users.


## External Nexus writer as a Python process

!!! warning
    This is intended for testing and should not be used in production. Caution: you may start more than one writer per session trying to write the same data. BLISS in unaware of writers started this way.

### Start the writer process

A session writer process (which serves one BLISS session) can be started inside the BLISS conda environment as follows

```bash
   $ NexusSessionWriter test_session --log=info
```

### Enable in BLISS

To allow for a proper Nexus structure, add these lines to the session's user script (strongly recommended but not absolutely necessary):

```python
    from nexus_writer_service import metadata
    metadata.register_all_metadata_generators()
```

The internal BLISS writer needs to be enabled in case you do not want to register the metadata generators

```python
    SCAN_SAVING.writer = 'hdf5'
```
