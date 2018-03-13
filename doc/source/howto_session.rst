.. _bliss-session-how-to:

Bliss session how to
====================

This chapter explains::
 * how to deal with bliss command line tool and sessions
 * how to create a BLISS custom session (named *eh1* in this example).
 * how to create a setup file to configure your session.


Commands
--------

Help
~~~~
Use ``-h`` flag to get help about bliss command line inteface::
    
    (bliss) pcsht:~/PROJECTS/bliss % bliss -h
     
    Usage: bliss [-l | --log-level=<log_level>] [-s <name> | --session=<name>]
           bliss [-c | --create-session=<name>]
           bliss [-v | --version]
           bliss [-h | --help]
           bliss --show-sessions
           bliss --show-sessions-only
    
    Options:
        -l, --log-level=<log_level>   Log level [default: WARN] (CRITICAL ERROR INFO DEBUG NOTSET)
        -s, --session=<session_name>  Start with some session
        -c, --create=<session_name>   Create a new session with the given name
        -v, --version                 Show version and exit
        -h, --help                    Show help screen and exit
        --show-sessions               Display available sessions and tree of sub-sessions
        --show-sessions-only          Display available sessions names only
 



Sessions list
~~~~~~~~~~~~~

To get the list of available sessions ::
     
     (bliss) pcsht:~/PROJECTS/bliss % bliss --show-sessions
     Available BLISS sessions are:
     cyril
     
     eh1

Other commands are also displaying the available sessions::
     bliss --show-sessions-only
     bliss -s

Version
~~~~~~~
Use ``-v`` or ``--version`` flag to get the current version of your BLISS installation::

    % bliss --version
    BLISS version 0.07





automatically
-------------

With the command ``bliss --create`` or ``bliss -c`` you can create the skeleton of a new session::

    bliss -c niouses

TO BE DONE...


manually
--------

Simple session
~~~~~~~~~~~~~~
Reminder: Take very good care to spaces in YAML files !

Session setup files are YAML files located in *beacon* configuration in a ``sessions`` sub-directory::

  % mkdir ~/local/beamline_configuration/sessions/

This directory must contain a ``__init__.yml`` file to indicate which plugin to use::

  % cat __init__.yml
  plugin: session

Just create a session setup YAML file (ex: ``eh1.yml``):

.. code-block:: yaml

  -class: Session
      name: eh1
      setup-file: ./eh1_setup.py

Create your python setup file (ex: ``eh1_setup.py``):

.. code-block:: python

  print "Welcome in eh1 BLISS session !!"

Then you can start your session::

    % bliss -s eh1
                           __         __   __
                          |__) |   | /__` /__`
                          |__) |__ | .__/ .__/


    Welcome to BLISS version 0.01 running on pcsht (in bliss Conda environment)
    Copyright (c) ESRF, 2015-2017
    -
    Connected to Beacon server on pcsht (port 3412)
    eh1: Executing setup...
    Initializing 'pzth`
    Initializing 'simul_mca`
    Initializing 'pzth_enc`
    Hello eh1 session !!
    Done.

    EH1 [1]:

*All objects* defined in your beacon beamline configuration directory (device or
sequence) will be loaded.

To selectively include objects
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Most of the time you don't want to have all objects declared in the
beacon configuration loaded in your session. So you can explicitly
indicate which objects must be included by using ``exclude-objects``
keyword followed by a list of objects:

.. code-block:: yaml

    - class: Session
      name: eh1
      setup-file: ./eh1_setup.py
      include-objects: [pzth, simul_mca]

The include-objects list can also be a classical YAML dash list.


To selectively exclude objects
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Conversely, you could also need to avoid to load unused objects using ``exclude-objects`` keyword:

.. code-block:: yaml

    - class: Session
      name: eh1
      setup-file: ./eh1_setup.py
      exclude-objects: [simul_mca, zzac]

The exclude-objects list can also be a classical YAML dash list.

To define custom sequences
~~~~~~~~~~~~~~~~~~~~~~~~~~

Just add ``.py`` files containing your sequences in a ``scripts/`` sub-directory of your ``sessions/`` directory::

  % mkdir ~/local/beamline_configuration/sessions/scripts/
  % cd  ~/local/beamline_configuration/sessions/scripts/
  % cat << EOF > eh1_alignments.py
 def eh1_align():
   print "aligning slits1"
   print "aligning kb"
   print "OK beamline is aligned :)"
 EOF

Load script file from the setup of your session::

  % cat ~/local/beamline_configuration/sessions/eh1_setup.py
  load_script("eh1_alignments")
  print "Hello eh1 session !!"

Now, ``eh1_align()`` script is available in *eh1* session:

.. code-block:: sourcecode

  EH1 [1]: eh1_align()
  aligning slits1
  aligning kb
  OK beamline is aligned :)



To add info in the toolbar
~~~~~~~~~~~~~~~~~~~~~~~~~~

To customize the toolbar of your session, you must define some special *Widgets* and insert them into the toolbar item list.

These widgets can represent:
 * A simple label
 * The status of an axis
 * The status of a Tango Attribute
 * The status or value of a special device (Insertion Device, Front-End, BEAMLINE)
 * Any result defined by a user-defined functions.

To include some of these widgets, you must define, in your setup file,
a *config function* decorated with the ``@configure`` decorator.

You can also add a *generic widget* to be used with a custom function.

Example to add a simple label, the position of a motor and a function to display time:

.. code-block:: python

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

This code will make your session to look like:

.. code-block:: sourcecode

 (bliss) pcsht:~ % bliss -s eh1
                        __         __   __          
                       |__) |   | /__` /__`         
                       |__) |__ | .__/ .__/         
 
 
 Welcome to BLISS version 0.01 running on pcsht (in bliss Conda environment)
 Copyright (c) ESRF, 2015-2017
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
 
 
 
 simot1: 12.05 | salut | Thu Dec 21 15:01:38 2017    


More widgets can be defined using the same model:

.. code-block:: python

        ugap = Attribute('UGap: ', 'CPM14-1B_GAP_Position', 'mm', None)
        fe_attrs = FEStatus.state, FEStatus.current, FEStatus.refill, FEStatus.mode

        repl.bliss_bar.items.append(FEStatus(attributes=fe_attrs))  # Front-End infos
        repl.bliss_bar.items.append(IDStatus(attributes=(ugap,)))   # Insertion Device position



You can switch for a more compact view (for compliant widgets like AxisStatus) with :

.. code-block:: python

        repl.bliss_bar_format = 'compact'

