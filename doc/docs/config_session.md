# BLISS sessions configuration

This chapter explains:

* how to create a BLISS custom session (named **eh1** in this example)
* how to configure a session
* how to add widgets to BLISS shell

## Manual creation of a new session

Session setup files are YAML files located in **beacon** configuration in a `sessions` sub-directory:

    % mkdir ~/local/beamline_configuration/sessions/

This directory must contain a `__init__.yml` file to indicate which plugin to use:

    % cat __init__.yml
    plugin: session

Just create a session setup YAML file (ex: `eh1.yml`):

    class: Session
        name: eh1
        setup-file: ./eh1_setup.py

!!! note
    Remember to take care with spaces in YAML files ;-)

Create a python setup file (ex: `eh1_setup.py`):

     print "Welcome in eh1 BLISS session !!"

Then a session can be started with `-s` option:

    % bliss -s eh1
                           __         __   __
                          |__) |   | /__` /__`
                          |__) |__ | .__/ .__/


    Welcome to BLISS version 0.02 running on pcsht (in bliss Conda environment)
    Copyright (c) ESRF, 2015-2018
    -
    Connected to Beacon server on pcsht (port 3412)
    eh1: Executing setup...
    Initializing 'pzth'
    Initializing 'simul_mca'
    Initializing 'pzth_enc'
    Hello eh1 session !!
    Done.
    
    EH1 [1]:

**All objects** defined in beacon configuration will be loaded.

## Session customization

### To include objects

Most of the time all objects declared in the beacon configuration
don't have to be loaded in a session. So they can be explicitly
included by using `config-objects` keyword followed by a list of
objects:

    - class: Session
      name: eh1
      setup-file: ./eh1_setup.py
      config-objects: [pzth, simul_mca]

!!! note
    The *config-objects list* can also be a classical YAML dash list.


### To selectively exclude objects

Conversely, objects could also be unnecessary so they can be
explicitly excluded by using `exclude-objects` keyword followed by a
list of objects:

    - class: Session
      name: eh1
      setup-file: ./eh1_setup.py
      exclude-objects: [simul_mca, zzac]

!!! note
    The *exclude-objects list* can also be a classical YAML dash list.

### To define custom sequences

Sequences contained in a `.py` files located in the
`sessions/scripts/` directory can be loaded with `load_script()`
command:

        % mkdir ~/local/beamline_configuration/sessions/scripts/
        % cd  ~/local/beamline_configuration/sessions/scripts/
        % cat << EOF > eh1_alignments.py
        def eh1_align():
          print "aligning slits1"
          print "aligning kb"
          print "OK beamline is aligned :)"
        EOF

To load a script file from the setup of a session:

        % cat ~/local/beamline_configuration/sessions/eh1_setup.py
        load_script("eh1_alignments")
        print "Hello eh1 session !!"

Now, `eh1_align()` script is available in **eh1** session:

        EH1 [1]: eh1_align()
        aligning slits1
        aligning kb
        OK beamline is aligned :)
