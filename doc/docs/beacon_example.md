### Example configuration

Here is an excerpt of the ESRF ID31 beamline configuration, as an example of a
real-world files structure:

    beamline_configuration/
        |
        ├── EH
        │   ├── detectors
        │   │   ├── diodes.yml
        │   │   ├── __init__.yml
        │   │   ├── maxipix.yml
        │   │   └── pilatus.yml
        │   ├── motion
        │   │   ├── aerotech.yml
        │   │   ├── eh.yml
        │   │   ├── energy.yml
        │   │   ├── iceid314.yml
        │   │   ├── iceid315.yml
        │   │   └── __init__.yml
        │   ├── samenv
        │   │   ├── furnace.yml
        │   │   ├── gasblower.yml
        │   │   ├── gasrig.yml
        │   │   ├── __init__.yml
        │   │   ├── ls336.yml
        │   │   └── pressure.yml
        │   ├── wagos
        │   │   ├── __init__.yml
        │   │   ├── wcid31gasload1.yml
        │   │   ├── wcid31l.yml
        │   │   └── wcid31o.yml
        │   └── __init__.yml
        ├── musst_prog                  #
        │   ├── acc_step_scan.mprg      # Any kind of file can be
        │   ├── contscan.mprg           # put in the configuration
        │   └── laser.mprg              #
        ├── OH1
        │   ├── motion
        │   │   ├── iceid311.yml
        │   │   └── __init__.yml
        │   ├── __init__.yml
        │   ├── transfocator.yml
        │   └── wbv1.yml
        ├── sessions
        │   ├── scripts
        │   │   ├── alignment.py
        │   │   ├── gasblower.py
        │   │   └── microstation.py
        │   ├── __init__.yml
        │   ├── sixc.py
        │   └── sixc.yml
        ├── beacon.rdb                  # Redis database automatic dump
        ├── frontend.yml
        ├── __init__.yml
        ├── multiplexer.yml
        ├── musst.yml
        ├── p201.yml
        ├── safety_shutter.yml
        └── undulator.yml


!!! note
    Non-YAML files are ignored by Beacon for creating objects and mappings, but a remote client can still retrieve any file. This is part of
    Beacon centralized file hosting.

#### Using Beacon API

##### Retrieving all objects names

    >>> from bliss.config.conductor import client as beacon
    >>> beacon.get_config_db_tree()
    <returns
    >>> file_like_object = beacon.remote_open(<filename>)
    >>> file_contents = file_like_object.read()
