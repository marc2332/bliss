# Usage of BLISS sessions

This chapter explains:

* how to deal with bliss command line tool and sessions
* how to create a BLISS custom session (named **eh1** in this example)
* how to create a setup file to configure a session.

## Commands

### Help
Use `-h` flag to get help about bliss command line inteface:

        % bliss -h
        Usage: bliss [-l | --log-level=<log_level>] [-s <name> | --session=<name>]
               bliss [-v | --version]
               bliss [-c <name> | --create=<name>]
               bliss [-d <name> | --delete=<name>]
               bliss [-h | --help]
               bliss --show-sessions
               bliss --show-sessions-only
        
        Options:
            -l, --log-level=<log_level>   Log level [default: WARN] (CRITICAL ERROR INFO DEBUG NOTSET)
            -s, --session=<session_name>  Start with the specified session
            -v, --version                 Show version and exit
            -c, --create=<session_name>   Create a new session with the given name
            -d, --delete=<session_name>   Delete the given session
            -h, --help                    Show help screen and exit
            --show-sessions               Display available sessions and tree of sub-sessions
            --show-sessions-only          Display available sessions names only



### Sessions list

Use  `-s` or `--show-sessions` option to get the list of available sessions:

     % bliss --show-sessions
     Available BLISS sessions are:
       cyril

Other commands are also displaying the available sessions:

     % bliss --show-sessions-only
     % bliss -s

### Version

Use `-v` or `--version` option to get the current version of a BLISS installation:

    % bliss --version
    BLISS version 0.2

## Automatic creation of a new session

Use `bliss --create` or `bliss -c` to create the skeleton of a new session:

    bliss -c eh1
    % bliss -c eh1
    creating 'eh1' session
    Creating: /bliss/users/guilloud/local/beamline_configuration/sessions/eh1_setup.py
    Creating: /bliss/users/guilloud/local/beamline_configuration/sessions/eh1.yml
    Creating: /bliss/users/guilloud/local/beamline_configuration/sessions/scripts/eh1.py


## Manual creation of a new session

Reminder: Take very good care to spaces in YAML files !

Session setup files are YAML files located in **beacon** configuration in a `sessions` sub-directory:

    % mkdir ~/local/beamline_configuration/sessions/

This directory must contain a `__init__.yml` file to indicate which plugin to use:

    % cat __init__.yml
    plugin: session

Just create a session setup YAML file (ex: `eh1.yml`):

    -class: Session
        name: eh1
        setup-file: ./eh1_setup.py

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

**All objects** defined in beacon configuration directory (device or
sequence) will be loaded.



## Session customization

### To selectively include objects

Most of the time all objects declared in the beacon configuration
don't have to be loaded loaded in a session. So they can be explicitly
included by using `include-objects` keyword followed by a list of
objects:

    - class: Session
      name: eh1
      setup-file: ./eh1_setup.py
      include-objects: [pzth, simul_mca]

The *include-objects list* can also be a classical YAML dash list.


### To selectively exclude objects

Conversely, objects could also be unnecessary so they can be
explicitly excluded by using `exclude-objects` keyword followed by a
list of objects:

    - class: Session
      name: eh1
      setup-file: ./eh1_setup.py
      exclude-objects: [simul_mca, zzac]

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



### To add info in the toolbar

To customize the toolbar of a session, special **Widgets** can be
defined and inserted into the toolbar item list.

These widgets can represent:

 * A simple label
 * The status of an axis
 * The status of a Tango Attribute
 * The status or value of a special device (Insertion Device, Front-End, BEAMLINE)
 * Any result defined by a user-defined functions.

A **config function** decorated with the `@configure` decorator, in
the setup file, indicate such a special widget.

A **generic widget** can also be used with a custom function.

Example to add a simple label, the position of a motor and a function to display time:

        from bliss.shell.cli import configure
        from bliss.shell.cli.layout import AxisStatus, LabelWidget, DynamicWidget
        from bliss.shell.cli.esrf import Attribute, FEStatus, IDStatus, BEAMLINE
        
        import time
        
        def what_time_is_it():
            return time.ctime()
        
        @configure
        def config(repl):
            repl.bliss_bar.items.append(LabelWidget("BL=ID245c"))
            repl.bliss_bar.items.append(AxisStatus('simot1'))
            repl.bliss_bar.items.append(DynamicWidget(what_time_is_it))

This code will make a session to look like:

     (bliss) pcsht:~ % bliss -s eh1
                            __         __   __          
                           |__) |   | /__` /__`         
                           |__) |__ | .__/ .__/         
     
     
     Welcome to BLISS version 0.02 running on pcsht (in bliss Conda environment)
     Copyright (c) ESRF, 2015-2018
     -
     Connected to Beacon server on pcsht (port 3412)
     eh1: Executing setup...
     Initializing 'simot1`
     Initializing 'pzth`
     Initializing 'simul_mca`
     Initializing 'pzth_enc`
     hello eh1 session !! 
     Done.
     
     EH1 [1]: 
     
     
     
     simot1: 12.05 | salut | Wed Apr 25 17:08:21 CEST 2018


More widgets can be defined using the same model:

        ugap = Attribute('UGap: ', 'CPM00-1B_GAP_Position', 'mm', None)
        fe_attrs = FEStatus.state, FEStatus.current, FEStatus.refill, FEStatus.mode

        repl.bliss_bar.items.append(FEStatus(attributes=fe_attrs))  # Front-End infos
        repl.bliss_bar.items.append(IDStatus(attributes=(ugap,)))   # Insertion Device position


To switch to a more compact view (for compliant widgets like AxisStatus), use:

        repl.bliss_bar_format = 'compact'


