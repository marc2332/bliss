

# BLISS measurement group



This chapter explains how to create and to deal with *measurement
groups*.

A measurement group is an object to wrap counters in it. The measurement group helps to deal with a
coherent set of counters.

For example, a measurement group can represent the counters related to
a detector, a hutch or an experiment.


## Creation

To create a measurement group, you can define it in the YML file of your session setup:

    - class: MeasurementGroup
      name: align_counters
      counters: [simct1, simct2, simct3]
  
    - class: MeasurementGroup
      name: MG1
      counters: [simct2, simct3]
  
    - class: MeasurementGroup
      name: MG2
      counters: [simct4, simct5]



## Usage

Once your measurement group is created, you can use it in a BLISS session:

    CYRIL [1]: align_counters
      Out [1]: MeasurementGroup:  align_counters (default)
   
                Enabled  Disabled
                -------  -------
                simct1
                simct2
                simct3


You can pass one or many measurement group as argument to a `scan` or `ct` procedure
to indicate which counters to use:

    CYRIL [20]: print MG1.available, MG2.available         #  4 counters defined
    ['simct2', 'simct3'] ['simct4', 'simct5']
    
    CYRIL [21]: timescan(0.1, MG1, MG2, npoints=3)
    Total 3 points, 0:00:00.300000 (motion: 0:00:00, count: 0:00:00.300000)
    
    Scan 15 Wed Feb 21 16:31:48 2018 /tmp/scans/cyril/ cyril user = guilloud
    timescan 0.1
    
               #         dt(s)        simct2        simct3        simct4        simct5
               0     0.0347409       0.50349      0.494272      0.501698      0.496145
               1       0.13725       0.49622      0.503753      0.500348      0.500601
               2        0.2391      0.502216      0.500213      0.494356      0.493359
    
    Took 0:00:00.395435 (estimation was for 0:00:00.300000)




### List of measurement groups

To get the list of all available measurement groups, you can use:

    CYRIL [23]: from bliss.common import measurementgroup
    
    CYRIL [24]: measurementgroup.get_all_names()
      Out [24]: ['align_counters', 'MG2', 'MG1']

### Active measurement group

If no measurement group is indicated to the scan, it uses a default
one : the `active measurement group`.

There is always only one active measurement group at the same time.

`ACTIVE_MG` is a global to know the measurement group which is
`active` at current time (same output than `align_counters`) :

    CYRIL [31]: ACTIVE_MG
      Out [31]: MeasurementGroup:  align_counters (default)
      
                Enabled  Disabled
                -------  -------
                simct2   simct1
                         simct3



This active measurement group is the one used by default by a `scan` or a `ct`:

    CYRIL [32]: ct(0.1)
    
    Wed Feb 21 15:38:51 2018
    
       dt(s) = 0.0161161422729 ( 0.161161422729/s)
      simct2 = 0.499050226458 ( 4.99050226458/s)

Only `simct2` is counting, the two others are disabled.


To change the active measurement group, use `set_active()` method:

    CYRIL [33]: ACTIVE_MG
      Out [33]: MeasurementGroup:  align_counters (default)
    
                 Enabled  Disabled
                 -------  -------
                 simct2   simct1
                          simct3
    
    CYRIL [34]: MG2.set_active()
    
    CYRIL [35]: ACTIVE_MG
      Out [35]: MeasurementGroup:  MG2 (default)
    
                  Enabled  Disabled
                  -------  -------
                  simct4
                  simct5


NB: the other way is a bit more complicated:

    CYRIL [10]: from bliss.common import measurementgroup
    CYRIL [11]: measurementgroup.set_active_name("MG2")




### Add/remove a counter to a measurement group

A counter can be added/removed to/from a measurement group.

    CYRIL [4]: MG1
      Out [4]: MeasurementGroup: MG1 (state='default')
                 - Existing states : 'default'
               
                 Enabled  Disabled
                 -------  -------
                 simct1   
                 simct2   
    
    CYRIL [5]: MG1.add(emeter2.counters.e1)
    
    CYRIL [6]: MG1
      Out [6]: MeasurementGroup: MG1 (state='default')
                 - Existing states : 'default'
               
                 Enabled  Disabled
                 -------  -------
                 simct1
                 simct2
                 e1
               
    
    CYRIL [7]: MG1.remove(emeter2.counters.e1)
    
    CYRIL [8]: MG1
      Out [8]: MeasurementGroup: MG1 (state='default')
                 - Existing states : 'default'
               
                 Enabled  Disabled
                 -------  -------
                 simct1
                 simct2


### Measurement group of measurement group

    CYRIL [1]: MG1
      Out [1]: MeasurementGroup: MG1 (state='default')
                 - Existing states : 'default'
               
                 Enabled  Disabled
                 -------  -------
                 simct1
                 simct2

    
    CYRIL [2]: MG1.add(MG2)
    
    CYRIL [3]: MG1
      Out [3]: MeasurementGroup: MG1 (state='default')
                 - Existing states : 'default'
               
                 Enabled  Disabled
                 -------  -------
                 simct1
                 simct2
                 MG2


### States


A measurement group can have many `states` to denote different usages. You can, for
example, disable some counters during an alignment and, in case of
problem, switch to the state where diagnostic counters are enabled.

At creation, a measurement group is in the `default` state:


    CYRIL [41]: align_counters
      Out [41]: MeasurementGroup:  align_counters (default) # <-- default state
      
                Enabled  Disabled
                -------  -------
                simct2   simct1         #   <-- counters simct1 and simct2
                         simct3         #       were previously disabled

You can create a new state in a measurement group with the `switch_state(<new_state_name>)` method:

    CYRIL [42]: align_counters.switch_state("diag_mono")
    
    CYRIL [43]: print align_counters
    MeasurementGroup:  align_counters (diag_mono)    #  new "diag_mono" state
    
    Enabled  Disabled
    -------  -------
    simct1                                           #  with all counters enabled
    simct2
    simct3


You can now customize the status of each counter within this state:

    CYRIL [46]: align_counters.disable = "simct3"

Use `state_names` propertie to get the list of available states:

    CYRIL [47]: align_counters.state_names
      Out [47]: ['diag_mono', 'default']

Then, you can switch from a state to another depending on your needs:

    CYRIL [50]: align_counters.switch_state("default")

    CYRIL [51]: print align_counters
    MeasurementGroup:  align_counters (default)

      Enabled  Disabled
      -------  -------
      simct2   simct1
               simct3

    CYRIL [52]: ct(1)
      Wed Feb 21 15:52:31 2018

         dt(s) = 0.00573420524597 ( 0.00573420524597/s)
        simct2 = 0.499528833799 ( 0.499528833799/s)


    CYRIL [53]: align_counters.switch_state("diag_mono")

    CYRIL [55]: print align_counters
    MeasurementGroup:  align_counters (diag_mono)

      Enabled  Disabled
      -------  -------
      simct1   simct3
      simct2


