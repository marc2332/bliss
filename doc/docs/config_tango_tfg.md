# Configuring the VME time frame generator card

This chapter explains how to configure the VME time frame generator (tfg) controller.
It assumes that you already have a running tfg2 tango device server on a vme system.

    Time Frame Generator controller
     
    Example YAML configuration:

    .. code-block:: yaml
    
        plugin: bliss
        class: TangoTfg2
        module: tango_tfg
        name: tfgtimer
        tango_uri: tfg2/tango/1     <-- tfg2 device server instance name (configured in Jive)
   

The following demonstrates the setup of an experiment comprising 40 frame pairs (1 pair is a dead frame followed by a live frame). The first 30 frames are 100ns dead and 0.1sec live followed by 10 frames of 100ns dead and 0.5 sec live. Acquisition is started by a falling edge TTL trigger signal in front panel input trigIn 0. Acquisition is restarted from the pause state by a falling edge TTL trigger signal in front panel input trigIn 1.
The tfg can also synchronise the acquisition of other equipment using output trigger signals in this case on every live frame.

    Usage:

    ALL_FRAMES = -1
    timing_info = {'cycles': 1,
                   'framesets': [{'nb_frames': 30,
                                  'latency': 0.0000001,
                                  'acq_time': 0.1},
                                 {'nb_frames': 10,
                                  'latency': 0.0000001,
                                  'acq_time': 0.5},
                                 ],
                    'startTrigger': {'name': 'TTLtrig0',
                                     'edge': 'falling',
                                     'debounce': 0.0,
                                     'threshold': 0.0,
                                    },
                    'pauseTrigger': {'name': 'TTLtrig1',
                                     'trig_when': [ALL_FRAMES,],
                                     'period': 'dead',
                                     'edge': 'falling', # default = rising
                                     'debounce': 0.0,   # default
                                     'threshold': 0.0,  # default
                                     },
                    'triggers': [{'name': 'xspress3mini',
                                  'port': 'UserOut0',
                                  'trig_when': [ALL_FRAMES,],
                                  'period': 'live',
                                  'invert': False,
                                  'series_terminated': False},
                                  ],
                    'scalerMode': 'Scaler64'
                    }

    >>> timer = TangoTfg2(name, config)
    >>> timer.prepare(timing_info)
    >>> timer.start()

## TFG Counters Configuration

When the tfg is used as a counter most of the timing_info configuration is handled by the counters.
Further information on configuring the TFG as a counter may be found in the module bm14/scanning/tfg.

However, as an example configuration we associate tfg channel addresses with counter names. 
Address 0 is mandatory as the Acquisition time.

 
    Example YAML configuration:

    .. code-block:: yaml
  
    name: tfg
    plugin: bliss
    package: bm14.scanning.tfg
    class: Tfg
    tango_uri: tfg2/tango/1
    channels:
      - name: AcqTime
        address: 0
      - name: I0
        address: 1
      - name: It
        address: 2
      - name: Iref
        address: 7
    calculations:
      - name: lnI0It
        numerator_address: 1
        denominator_address: 2
