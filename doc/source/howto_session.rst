.. _bliss-session-how-to:

Bliss session how to
====================

This chapter explains::
 * how to create a BLISS custom session (named *eh1* in this example).
 * how to create a setup file to configure your session.


automatically
-------------

TODO : bliss add_session script

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



To add info in a toolbar
~~~~~~~~~~~~~~~~~~~~~~~~


