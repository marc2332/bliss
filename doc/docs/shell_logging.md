# BLISS shell logging

## Presentation

There are two kind of logging in bliss:

* Module logging
* Instance logging

### Module logging

Is the standard python "way of logging" in which every logger has the name of the python module that is producing it.
The hierarchy is given by the files organization inside the bliss project folder.

        BLISS MODULE LOGGERS             
        module               level    set
        ==================== ======== =====
        bliss                WARNING  YES
        bliss.config         WARNING  -
        bliss.common.mapping WARNING  -
        bliss.scans          WARNING  -
        bliss.shell          WARNING  -
        bliss.standard       WARNING  -


### Instance logging

Is a specific Bliss logging in which every logger has a name that represents the instance hierarchy.

        BEAMLINE INSTANCE MAP LOGGERS
        instance                                                       level    set
        ============================================================== ======== =====
        beamline                                                       WARNING  YES  
        beamline.comms                                                 WARNING  -  
        beamline.counters                                              WARNING  -
        beamline.devices                                               WARNING  -
        beamline.devices.8d6318d713ee6beb322b8dde                      DEBUG    YES
        beamline.devices.8d6318d713ee6beb322b8dde.axis.hooked_error_m0 DEBUG    -  
        beamline.devices.8d6318d713ee6beb322b8dde.axis.hooked_m0       DEBUG    -
        beamline.devices.8d6318d713ee6beb322b8dde.axis.hooked_m1       DEBUG    -
        beamline.devices.8d6318d713ee6beb322b8dde.axis.jogger          DEBUG    -
        beamline.devices.8d6318d713ee6beb322b8dde.axis.m0              DEBUG    -
        beamline.devices.8d6318d713ee6beb322b8dde.axis.m1              DEBUG    -
        beamline.devices.8d6318d713ee6beb322b8dde.axis.m2              DEBUG    -
        beamline.devices.8d6318d713ee6beb322b8dde.axis.omega           DEBUG    -
        beamline.devices.8d6318d713ee6beb322b8dde.axis.roby            DEBUG    -
        beamline.devices.8d6318d713ee6beb322b8dde.axis.s1b             DEBUG    -
        beamline.devices.8d6318d713ee6beb322b8dde.axis.s1d             DEBUG    -
        beamline.devices.8d6318d713ee6beb322b8dde.axis.s1f             DEBUG    -
        beamline.devices.8d6318d713ee6beb322b8dde.axis.s1u             DEBUG    -
        beamline.sessions                                              WARNING  -

The relevant informations are:

* logger name: name that represents the module (for module loggers) or the instance (for instance map loggers)
* logger level: python standard logging levels (logging.INFO, logging.ERROR, ...)
* set: YES if the logging level is set for that particular level, '-' if the level is inherited from the upper levels

## Useful Commands

### Devices and instances

Probably the most convenient way to activate logging for a specific device is from the _logger method of the device itself:

        BLISS [1]: m0 = config.get('m0')

        BLISS [2]: m0._logger.debugon()

        BLISS [3]: lsdebug()
        NO bliss loggers for DEBUG level !!



        BEAMLINE INSTANCE MAP LOGGERS
        instance                                                  level    set  
        ========================================================= ======== =====
        beamline.devices.8d6318d713ee6beb322b8dde.axis.m0 DEBUG    YES  

        BLISS [4]: m0._logger.debugoff()

        BLISS [5]: lsdebug()
        NO bliss loggers for DEBUG level !!



        NO map loggers for DEBUG level !!

Activating debug from one specific device may not give the desired informations as a device could be managed by a controller and a controller may handle a communication.
To collect all informations activate debug at the higher level, usually for the controller.

        log.debugon('8d6318d713ee6beb322b8dde')



## log

The class container for log commands.

### log.lslog() or lslog()

```lslog("glob name")```

It can be used without arguments to display all loggers or with a glob pattern to apply a filter.
Glob is the particular naming match used usually inside linux and windows shells. The two most used wildcards are * and ? matching respectively 'any number of characters' and 'one character', but a lot more can be used (see Glob/Globbing documentation).

Example of calling lslog without arguments:

        BLISS [1]: lslog()
        BLISS MODULE LOGGERS
        module               level    set  
        ==================== ======== =====
        bliss                WARNING  YES  
        bliss.common.mapping WARNING  -    
        bliss.scans          WARNING  -    
        bliss.shell          WARNING  -    
        bliss.standard       WARNING  -    



        BEAMLINE INSTANCE MAP LOGGERS
        instance          level    set  
        ================= ======== =====
        beamline          WARNING  YES  
        beamline.comms    WARNING  -    
        beamline.counters WARNING  -    
        beamline.devices  WARNING  -    
        beamline.sessions WARNING  -    

Example of calling lslog with a glob argument:

        BLISS [5]: lslog('*com*')
        BLISS MODULE LOGGERS
        module               level    set  
        ==================== ======== =====
        bliss.common.mapping WARNING  -    



        BEAMLINE INSTANCE MAP LOGGERS
        instance       level    set  
        ============== ======== =====
        beamline.comms WARNING  - 

### log.lsdebug() or lsdebug()

```lsdebug()```

Shows loggers currently in debug mode:

        BLISS [10]: lsdebug()
        NO bliss loggers for DEBUG level !!



        BEAMLINE INSTANCE MAP LOGGERS
        instance          level    set  
        ================= ======== =====
        beamline.counters DEBUG    YES 

### log.debugon()

```log.debugon("logger name or part of it")```

Activates debug for a specific logger name, it will match also if is only a part of the logger name is given.

        BLISS [22]: log.debugon('hooked')
        NO bliss loggers found for [hooked]
        Set logger [beamline.devices.8d6318d713ee6beb9efbb5be322b8dde.axis.hooked_error_m0] to DEBUG level
        Set logger [beamline.devices.8d6318d713ee6beb9efbb5be322b8dde.axis.hooked_m0] to DEBUG level
        Set logger [beamline.devices.8d6318d713ee6beb9efbb5be322b8dde.axis.hooked_m1] to DEBUG level

### log.debugoff()

```log.debugoff("logger name or part of it")```

Like debugon() but sets the logging level for that logger name to the global defined one.

        BLISS [23]: log.debugoff('hooked')
        NO bliss loggers found for [hooked]
        Remove DEBUG level from map logger [beamline.devices.8d6318d713ee6beb9efbb5be322b8dde.axis.hooked_error_m0]
        Remove DEBUG level from map logger [beamline.devices.8d6318d713ee6beb9efbb5be322b8dde.axis.hooked_m0]
        Remove DEBUG level from map logger [beamline.devices.8d6318d713ee6beb9efbb5be322b8dde.axis.hooked_m1]
