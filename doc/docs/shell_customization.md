
BLISS shell
===========


Useful commands
---------------

Functions that can help to customize a BLISS session.


* Current session name: `get_current().name`
* Beamline name: `BEAMLINE`



Color scheme
------------

BLISS terminal color scheme can be changed by adding :

    repl.use_code_colorscheme('pastie')
to the config file (`sessions/scripts/<session>.py`) of the session.

example :

    from bliss.shell.cli import configure
    
    @configure
    def config(repl):
        repl.bliss_bar.items.append(LabelWidget("BL=ID42c"))

        # Color scheme change.
        repl.use_code_colorscheme('pastie')

Terminal scrolling
------------------

Symptom: Can not scroll up in the BLISS session terminal

Issue: Trying to scroll up on some terminal is immediately canceled by
a return to the the last line.

* Fix for xfce4-terminal:

        Fix: Edit-> Preferences -> General: Untick `Scroll on output`
	         Click on `Close` and "Voila !"


Toolbar customization
---------------------

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
        def config_widgets(repl):
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
     
     
     
     BL=ID245c | simot1: 12.05 | Wed Apr 25 17:08:21 CEST 2018


More widgets can be defined using the same model:

     ugap = Attribute('UGap: ', 'CPM00-1B_GAP_Position', 'mm', None)
     fe_attrs = FEStatus.state, FEStatus.current, FEStatus.refill, FEStatus.mode

     repl.bliss_bar.items.append(FEStatus(attributes=fe_attrs)) # Front-End infos
     repl.bliss_bar.items.append(IDStatus(attributes=(ugap,)))  # ID position


To switch to a more compact view (for compliant widgets like AxisStatus), use:

     repl.bliss_bar_format = 'compact'


