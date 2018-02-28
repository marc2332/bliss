.. _bliss-measurement_group-how-to:

Bliss measurement group how to
==============================

This chapter explains how to create and deal with *measurement groups* (MG).

A measurement group is an object to wrap counters in it. The measurement group helps to deal with a coherent set of counters.

For example, a measurement group can represent counters related to a detector, a hutch or an experiment.


Creation
--------
To create a measurement group, you can define it in the YML file of your session setup:

.. code-block:: yaml

  - class: MeasurementGroup
    name: align_counters
    counters: [simct1, simct2, simct3]

  - class: MeasurementGroup
    name: MG1
    counters: [simct2, simct3]

  - class: MeasurementGroup
    name: MG2
    counters: [simct4, simct5]


Usage of measurement group
--------------------------

Once your measurement group is created, you can use it in a BLISS session::

 CYRIL [1]: align_counters
   Out [1]: MeasurementGroup:  align_counters (default)

             Enabled  Disabled
             -------  -------
             simct1
             simct2
             simct3

The measurement group can be passed to a `scan` or `ct` procedure to
define counters to process::

   CYRIL [4]: ascan(simot1, -2, 2, 7, 0.1, align_counters)
   Total 7 points, 0:00:09.500000 (motion: 0:00:08.800000, count: 0:00:00.700000)

   Scan 5 Wed Feb 21 15:26:31 2018 /tmp/scans/cyril/ cyril user = guilloud
   ascan simot1 -2 2 7 0.1

              #         dt(s)        simot1        simct1        simct2        simct3
              0       4.18972            -2      0.501319     0.0165606    0.00511711
              1       5.12933         -1.33      0.728287     0.0236184     0.0073165
              2       6.06347         -0.67      -0.33863      0.257847      0.251785
              3       6.98862             0     -0.608677       1.01518      0.997982
              4       7.92987          0.67      -2.29062      0.261047      0.249959
              5       8.86126          1.33      0.219424      0.023286     0.0137307
              6       9.78928             2     -0.558003    0.00988632     0.0165549

   Took 0:00:09.993863 (estimation was for 0:00:09.500000)

You can pass one or many measurement group as argument::

    CYRIL [20]: print MG1.available, MG2.available         #  4 counters defined in 2 MG
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


Active measurement group
------------------------

If no measurement group is indicated to the scan, a default one is
used: the *active measurement group*.

There is always only one active measurement group at the same time.

``ACTIVE_MG`` is a global to know the measurement group which is
`active` at current time (here, the output is the same than
``align_counters`` one) ::

 CYRIL [1]: ACTIVE_MG
   Out [1]: MeasurementGroup:  align_counters (default)

             Enabled  Disabled
             -------  -------
             simct1
             simct2
             simct3


This *active measurement group* is the one used by default by a `scan` or a `ct`::

    CYRIL [32]: ct(0.1)

    Wed Feb 21 15:38:51 2018

       dt(s) = 0.016116142272 ( 0.16116142272/s)
      simct2 = 0.499050226458 ( 4.99050226458/s)
      simct3 = 0.591432432452 ( 5.91432432452/s)


To change the *active measurement group*, use ``set_active()`` method::

    CYRIL [33]: ACTIVE_MG
      Out [33]: MeasurementGroup:  align_counters (default)

                 Enabled  Disabled
                 -------  -------
                 simct1
                 simct2
                 simct3

    CYRIL [34]: MG2.set_active()

    CYRIL [35]: ACTIVE_MG
      Out [35]: MeasurementGroup:  MG2 (default)

                  Enabled  Disabled
                  -------  -------
                  simct4
                  simct5



Counters states
---------------

Within a measurement group, you can *disable/enable* one or many counters.

The activation/desactivation can be done by giving the *name* of the
counter or the *counter object*.

Example to disable one counter by name::

   CYRIL [5]: align_counters.disable("simct1")

Example to disable many counters by names::

  CYRIL [6]: align_counters.disable("simct2","simct3")

And to re-enable one::

   CYRIL [7]: align_counters.enable("simct2")

Now, there is 1 counter enabled and 2 disabled::

   CYRIL [8]: print align_counters
   MeasurementGroup:  align_counters (default)

              Enabled  Disabled
              -------  -------
              simct2   simct1
                       simct3

It's also possible to enable/disable counters by *objects* (note the abscence of
quote around simct5)::

    CYRIL [19]: simct2
      Out [19]: <AutoScanGaussianCounter object at 0x7fc9b415e450>

    CYRIL [20]: align_counters.enable(simct2)


To enable / disable all counters at once::

    CYRIL [15]: align_counters
      Out [15]: MeasurementGroup:  align_counters (default)

                  Enabled  Disabled
                  -------  -------
                  simct1
                  simct2
                  simct3


    CYRIL [16]: align_counters.disable_all()

    CYRIL [17]: align_counters
      Out [17]: MeasurementGroup:  align_counters (default)

                  Enabled  Disabled
                  -------  -------
                           simct2
                           simct3
                           simct1


Measurment Group States
-----------------------

A *measurement group* can also have many *states* to denote different
usages. You can, for example, disable some counters during an
alignment and, in case of problem, switch to another state with
``switch_state()`` command where diagnostic counters are enabled.

At creation, a measurement group is in the *default* state::

  CYRIL [41]: align_counters
    Out [41]: MeasurementGroup:  align_counters (default)     #   <-------- default state

              Enabled  Disabled
              -------  -------
              simct2   simct1         #   <-------- counters "simct1 and simct2" were previously disabled
                       simct3

You can create a new state in a measurement group with the ``switch_state(<new_state_name>)`` method::

    CYRIL [42]: align_counters.switch_state("diag_mono")

    CYRIL [43]: print align_counters
    MeasurementGroup:  align_counters (diag_mono)    #  new "diag_mono" state

    Enabled  Disabled
    -------  -------
    simct1                                           #  with all counters enabled
    simct2
    simct3

You can now customize the state of each counter within the measurment group state::

    CYRIL [46]: align_counters.disable('simct3')

Use ``state_names`` propertie to get the list of available states::

    CYRIL [47]: align_counters.state_names
      Out [47]: ['diag_mono', 'default']

And then, you can switch from a state to another depending on your needs::

    CYRIL [50]: align_counters.switch_state('default')

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
