Open the [Nexus compliant](https://www.nexusformat.org/) HDF5 file written by the [Nexus writer](dev_data_nexus_server.md) with [silx](http://www.silx.org/)

## From Bliss Shell

Silx can be launched from inside bliss using:

```python
BLISS [1]: silx_view()
```

If at least one scan was performed in the current session, the command will open
as a default the last scan (`SCANS[-1]`).

As an option you can specify which scan to open passing it as an argument:

```python
BLISS [7]: silx_view(SCANS[-3])
```

## From System Shell

Be sure to activate the proper conda environment and type:

```bash
silx view /data/visitor/hg123/id21/sample/sample_0001/sample_0001.h5
```


!!! warning
    Do not use a silx version older than 0.12.0
