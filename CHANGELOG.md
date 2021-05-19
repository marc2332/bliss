# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Flint
    - Added dedicated widget for acqobj exposing 1D data
        - Only 1D data from this acqobj is displayed
        - Supports metadata from controllers or acqobj to custom the X-axis
            - `xaxis_channel`, `xaxis_array`
    - Added data display as index for curve plots and onedim plots
    - Group MCA channels per detectors in the curve plot property tree
    - Added histogram tool when displaying image in custom plots
    - Added a content menu option to center profile ROIs in image/scatter
    - Added curve stack as custom plot
    - Added an overlay with size of Lima rect ROIs
    - Added tools to duplicate/rename ROIs during ROI edition
    - Better handling of timeout, and try not to have 30s
    - Better handling of stucked state
        - Added `restart_flint` command from `bliss.common.plot`
        - Added `restart_if_stucked` argument to `get_flint()` (False by default)
        - Added `restart_flint_if_stucked` attribute to `SCAN_DISPLAY`, used when
          `auto=True`
    - Monitoring problems
        - Added `USR1` and `USR2` signals to interrupt and log internal information
        - Added `--enable-watchdog` command line argument to log and kill Flint if
          too much memory is used
    - `scan_info["requests"]` is not anymore read (replaced by `channels`)
    - Update to silx 0.15.1
- Demo
    - Added regulation mock to the demo session
- Scan publication
    - Added device/channel metadata to the `scan_info`
    - Added a `PREPARED` event with an updated scan_info
    - `AcqObj.fill_meta_at_scan_start` is used to fill to `scan_info`
    - Added metadata `type` for Lima detector and MCAs
    - Added `ScansWatcher` and `ScansObserver` to replace `watch_session_scans`

### Changed

- Flint
    - When Flint is not fast enough to reach data from Redis, NaN values
      are used in order to keep the data alignment
- XIA mca
    - Logger improved (can log at handel lib and BLISS levels)
    - Run server according to config retrieved from beacon
    - Client re-connection on server restart
    - Improved management of current_configuration / default_configuration
- Project: Remove `-conda` suffix from requirement files

### Fixed

- Flint
    - Fixed slow rendering occurred on live curves and scatters with fast scans
    - The video image is now also used for Lima EXTRERNAL_TRIGGER and EXTERNAL_GATE
    - Fixed blinking of the regulation plot legend
    - Fixed undisplayed ROIs during a scan. A tool is provided to display them
      if not already selected.
    - Fix update of the property view after an update of the backend

### Removed

## [1.7.3 - 2021-03-22]

### Added

- BCDU8 controller
- HMC8041 power supply
- more complete Aerotech Soloist support
- Lima
    - addons for Eiger camera
    - more explicit "no saving" enum
    - Andor3 camera
    - add access to BufferSize/MaskFile on RoiCounters
    - new roi counters collection support
- Wago modules catalogue: 750-342,352,363,515
- Writer
    - explicit exception if parent node is missing
    - OFF and RUNNING states, now means respectively "not listening to events and resources released" and "writer alive"

### Changed

### Fixed

- calculation counters with 1D or 2D inputs or outputs
- motor controller hardware initialization call, in case motor controller had no name
- filter set transmission calculation
- auto filters
- CT2
    - memory leak and excessive memory reallocations
- MCA
    - refresh rate bug for Xia Falcon X
    - memory leak with cumulated MCA data in MCA counters
- PM600: steps_position_precision fix (defaults to 1)
- PI E712: position offset
- PI E727: connection refused happening sometimes
- Symetrie hexapod: wrong units
- xyonrotation controller
- Regulation
    - avoid hardware call in "_store_history_data"
    - last output value when in deadband
    - Oxford 700 and 800 communication issues
- Pace controller communication
- Flint
    - memory leak with regulation plots
    - ignore timeout in regulation plots
    - Fix storage of line profiles in the image/scatter plot
    - matplotlib patching to avoid memory leak
- data publishing: too many KEYS calls
- limatake __info__

 
### Removed

## [1.7.2 - 2021-01-26]

### Added

### Changed

### Fixed

- scan metadata: add missing 'technique' field
- rpc: return None for object type if connection is not established
- aliases: report errors via debug log message
- Lima
    - never fail when retrieving counters, if Lima server is off
    - Eiger detector: use TRIGGER synchronization mode
    - BPM: ensure BPM task is stopped, if no BPM calculation is asked
- ct2
    - fix inheritance bug introduced in 1.7.0 by using delegation
    - release CPU pressure by buffering acq. data
- musst
    - cache "event buffer size"
    - release CPU pressure in reading loop
    - filter bad EPTR values, sometimes received from the device
- default max publishing time set to 0.2 seconds
- fix 'fcntl' import (Windows)
- "ct" display: handle numbers with a lot of digits and sign
- spec motor controler: removed bad SpecClient import
- icepap: warning message in case of close loop Settling Timeout error
- calc. motors: fix when motors are already on target
- mca: fix for block_size set to None
- oxford cryo: fix missing lazy initialization call
- timescan, loopscan: fix 'sleep_time' argument
- moco: disable ECHO mode
- icat: fix newsample, newdataset
- measurement group: when device is enabled, use all counters if there is no default counters
- axis: initialize set_position with controller position, even if read mode is "encoder"
- Flint: workspace saving/loading fix

### Removed

## [1.7.0 - 2021-01-04]

### Added

- Axis
    - new `velocity_low_limit` and `velocity_high_limit` settings
    - disable (= no communication at all) if controller cannot initialize, or if axis cannot initialize
        - call `enable()` to try again when problem is solved
- Controllers
    - Tektronix oscilloscope support
    - Vacuum gauge
- Documentation    
    - added info on "tcp proxy" (for PI piezos in multiple sessions, for example)
    - PEPU documentation
- Controllers
    - attocube AMC 100
    - icepap: multiple encoders reading optimization
- Core
    - frequency option to sampling counters, and reasonable defaults (1 Hz, or more depending on the controller)
- Flint
    - Display ROI geometries with the detector image widget during a scan
    - Allow to switch OpenGL/matplotlib from "Display" menu
        - This setting is saved in a config file in the computer per user
        - Added `--disable-opengl`
    - Autoscale +/-3stddev on colormap is now clamped with the input data range
    - Arc ROI is provided with 2 interactive modes: 3 points (default) or polar mode
    - Refresh rate are displayed in both period and frequency
    - Display scatter and image size in the plot title
    - Workspace
        - Rework the way workspace are managed
        - Rework the workspace menu and provide an explicit "save" action
        - Better handling of the workspace state
        - Image profile selection is saved/restored (experimental)
        - Workspace are now anymore session dependent
- Scan description (`scan_info`)
    - `bliss.scanning.scan_info.ScanInfo` was created in order to replace
      scan_info dictionary and ScanInfoFactory
    - A `set_sequence_info` helper was added to define the amount of excepted
      scans from a sequence
    - Creates a `channels` structure for metadata like `display_name` and `unit`
    - Provides ROI geometry
- Standard functions
    - timestamp for `last_error()`
- Motion hooks
    - new `pre_scan`, `post_scan` methods
- Nexus Writer
    - profiling using yappi
- Wago hook: added `__info__`

### Changed

- aliases can now be created in YML config files, directly from object if it has only 1 counter
- Controllers
    - actuators: handle devices with no state reading (in/out)
    - CT2: configuration is loaded on the server side
    - new KB controller (focusing procedure)
    - NewFocus controller refurb.
    - multiple positions controller: show positions while moving
    - Wago: show host in connection error message
- Scanning
    - automatically add encoders, if any, for axes in for standard scans
- Documentation
    - regulation and temperature frameworks clearly separated
    - MCA documentation update
- Flint
    - Skip warning about missing elogbook when BLISS is used as library
    - Workspaces are not anymore automatically saved between Flint executions,
      and explicit "save" action is provided in the "workspace" menu
- Nexus Writer
    - better error message when file is locked
    - pin-point h5py library to version 2.10
- Standard functions
    - better output for `ct()`
    - disable soft axes from positioners and axes displayed with `wa()` by default
- Temperature => Regulation
    - nanodac fully integrated in regulation framework
    - oxford controllers

### Fixed

- Beacon web portal
    - buttons to work outside ESRF
- Beacon channels
    - initialization optimisation (via pipeline)
- Controllers
    - Beam shutter `close` error if hutch is not searched
    - CT2
        - too many RPC calls for `__info__`
        - allow channel 10 to be used as a counter
        - blocking acquisition loop
    - icepap shutter: initialization blocks forever
    - lakeshore: "EOL" fix
    - Machine Current: makes Tango proxies too often, SR_mode can return -1
    - MUSST: wrong channel for icepap switch
    - PI-E517 error when closing loop
    - PM600: serial communication fix
    - Wago: interlock fixes, allow FS for analog output channels
    - xia: decouple sending current pixel data and acquisition polling
- Core
    - remove invalid use of runtime interface discovery (protocol), that is doing hw access when traversing devices map
- Data publishing
    - synchronization issue with streams
    - change `idle` to `sleep(0)`: ensure data to be published when CPU usage is high
    - scan groups and caching race condition
    - optimisation of devices preparation in scans
    - CPU intensive publishing
- elogbook
    - do not show error message when there is no metadata server
- Flint
    - Data from Lima detectors and MCAs are not anymore hidden on a `amesh` scan
    - Data from MCAs are again displayed inside an MCA widget
    - Data from Lima detectors and MCAs from a sub scan of a sequence are not
      anymore hidden
    - Fixed vmax on `set_plot_colormap` remote API
    - Fixed initial ROIs provided as a dict
- ICAT
    - allow single motors in "positioners" group
    - fix race condition with metadata gathering and parallel scans
    - attenuator metadata compliant with ICAT
- Lima
    - dexela: use "image" synchro
    - frelon: update size
- Nexus Writer
    - fix wrong timestamp (+1 hour)
    - scan info can contain npoints and data_dim while missing npoints{i}
    - inconsistency in ROI naming
    - fix Tango timeouts
    - "DIS" positions reported in positioners
- Regulation framework
    - start ramping from current input value
    - less hardware calls when ramping
- RPC
    - extend read buffer to 128 KB
    - service: load the package in case of local beamline controllers
    - unneeded calls to `__eq__`, `__hash__`, `__neq__`
- Shell
    - progress bar synchronization problem
    - step scan data watch optimization
- Standard functions
    - `goto_cen()` fix for "step"-like data (#2230)
    - `umv`: fixed error message when move fails

### Removed

- ID31 specific controller (fuelcell)
- MX-specific Flex controller

## [1.6.0 - 2020-10-25]

### Added

- ICAT metadata can now be saved to ICAT
- Controllers
    - shutter can be now used in cleanup context managers (will close the shutter on cleanup)
    - Micos motor controller: add steps_position_precision
    - Symetrie hexapod: added `origin` and `user_origin` options in YML config
    - Keithley temperature sensor
    - wago: added modules 750-464 & 750-473
    - Elmo: added support for linear motors
    - Stackmotors: pair of motors mounted on top of each other
- Flint
    - A splash screen to wait for start up
    - A scan sequence can now display plots
    - Extra items (fit, derivative) from default curve plot will be inherited
      into the next scan
    - Irregular scatters can be displayed with a solid rendering using 2D
      histogram
    - n-dim scatters can be displayed in 2D if extra dimensions are steppers
      (if behave like many frames, only the last one is displayed)
    - Dedicated widget to display data from profile ROIs
    - Added negative function filter on curves
    - The colormap is now part of the live image/scatter widget configuration
      and reused for each new scans
    - The colormaps from live plots are now editable in a common dockable widget
    - Logs are saved using beacon service (`/var/log/bliss/flint_{session}.log`)
    - Remote Flint API
        - Added `get_plot` and `get_live_plot` from `flint()` proxy to create and
          retrieve plots
        - Provides a `set_colormap` method to custom live image/scatter plots
        - Provide `focus` method to set the focus to a plot
        - Provide a method to export a plot to the logbook
        - Provide `update_user_data` method to feed live plot with processed data
          from BLISS shell
- Lima
    - Provide codecs for few RGB format from Lima video image
        - To use it, an optional dependency 'opencv' have to installed in the env
    - Arc rois (for sinograms)
    - Update `edit_roi_counters` to also edit ROIs from Lima roi2spectrum (roi profile)
      and arc ROIs
    - new Eiger camera class
- Nexus Writer
    - NXData with default plot following plotinit, plotselect in HDF5 file
    - MCA counters in NXDetector
- Redis
    - added option to start 2 databases, one for settings one for data
    - client-side caching to optimize settings
- RPC
    - Easily expose bliss object through server service
- Scans
    - custom scan math functions
        - `find_position` and `goto_custom` take an user-supplied callback
    - Custom scan description (`scan_info`)
        - Added fields to explicitly describe scatter plots
        - Added fields to group channels of the same size
        - Added fields to describes complex scatters
        - Added `axis-id` to order the scatter axis
    - chain: add `before_stop` hook just before stopping devices
    - display filename, scan number and date at the beginning of a scan
    - CT2: new acquisition master for Variable Integration time in step scans for p201 and calc counters linked to p201
    - improved scan statistics
        - added metadata to timing measure
        - include `wait_reading` timing
    - ESRF data policy event channel
    - AutoFilter providing a step-by-step ascan which can repeat counting to fit with the countrate range by changing the filter provided by the FilterSet controller behind
- Standard functions
    - added `pprint`
    - added `rockit`
    - umvd, umvdr, mvd, mvdr: functions for moving in dial position

### Changed

- references in configuration YML files are now evaluated on demand, not only once
- lprint, ladd renamed to user_print or elog_print and elog_add
- expression-based calc counters can now have their constants as configuration references
- Axis
    - Indicate position when hard limit is reached
- BLISS commands
    - `edit_roi_counters` now set the focus on the detector widget
- Controllers
    - machinfo "wait for refill" is no longer shared between multiple sessions
    - nanodac moved to Regulation framework
    - icepap: take stop code into account (put controller in FAULT state)
    - symetrie hexapod: added timeout argument in connecto
    - MCCE refactoring
        - serial object configuration to use official get_comm
        - Manage retry in case of timeout
        - Add range as string
    - move moco motor code in `bliss.controllers.motors.moco` instead of `bliss.controllers.moco`
- Flint
    - On a new scan, the focus is set to a widget, only if the scan is not
      visible on one of them
    - On live curve plot property, clicking on radio button when it is already
      checked will remove the curve
    - Custom scan description (`scan_info`)
        - `fast`/`slow` axis kind was replaced by `axis-id`
        - Axis kind only contains `forth/backnforth/step`
- Lima
    - accumulation parameters for Lima devices are now controller parameters, and handled via a Beacon object (saved in redis)
    - image and roi dialogs
- Redis
    - turned on I/O threads for data
    - data is not persisted to disk anymore (when the second redis DB is used)
- Scans
    - scan_saving: remove tango manager status from the display table
    - SCAN_SAVING.dataset moved to SCAN_SAVING.dataset_name, SCAN_SAVING.dataset now represents
      an object handling icat metadata of the dataset
    - SCAN_SAVING.sample moved to SCAN_SAVING.sample_name
    - SCAN_SAVING.proposal moved to SCAN_SAVING.proposal_name
- Tango MetadataManager device
  - latest version of MetadataManager(4.0.7) required.
  - by default datasets are no longer in `running` state on MetadataManager. Instead they are
    pushed including their metadata once the dataset is closed.
- tmux
    - independent tmux servers & sockets are used for diffrent sessions this way
      the tmux process of one session can be killed without affecting the otheres
    - the default session will no longer use tmux as it is meant for dev. and
      debug usage. It is not expected to have seral useres in these sessions
- Tests
    - improved dangling greenlets monitoring

### Fixed

- Fixed first motor position for `amesh` with backnforth enabled
- Fixed memory leak on Tango DeviceProxy
    - Used by Redis stream client retrieving image from node (like Flint)
- `user_script_load` now really reloads the script file
- aliases: avoid object comparisons with == as it calls __eq__
    - potentially on remote objects
- modbus communication fix
- too many opened file descriptors because of channels initialization
- Axis
    - ensure no communication with hardware if movement does not happen (for example, if movement is too small)
    - NoSettingsAxis in calc. controller
    - NoSettingsAxis missing settings
    - prevent recursion when settings are set
- Beacon configuration application
    - documentation search bar not working in Firefox
- Controllers
    - wago interlocks: fixed a bug on names longer than 32 chars
    - Moco move state
    - machinfo
        - counters now show in measurement group
        - metadata saving when session is restarted
    - speedgoat: prevent movement when already in position
    - nhq communication parsing
    - white beam attenuator dialog
    - oxford800 info and doc
    - Mythen detector support
    - Eurotherm 2000 also works with 32XX models
    - Linkam
    - P201/CT2: fix `acq_count_time` not defined when in ExtGate
    - icepap trajectory: do not require velocity and acceleration in config
    - MUSST counters
    - ESRF Undulators
- Flint
    - Fixed memory leak on tree property and data
    - Fixed plot display in order to always use `plotselect` selection
    - Fixed `plotselect` was requesting Flint creating with some conditions
    - Fixed inconsistency with Flint layout at startup. Now the exact same
      layout is supposed retrieved
    - Fixed Flint segmentation fault on GLX initialization
    - Fixed default selected x-axis on ascan scans
    - Fixed black background on OpenGL rendering
    - Fixed display of statistics on curves using integer array
    - Fixed displayed mask after the user mask selection
- Lima
    - Frelon "frame transfer" mode
    - Perkin Elmer "synchro" mode to IMAGE + EXTERNAL_START_STOP trigger mode
    - operations on image (flipping, binning, rotation) vs ROIs
- Nexus Writer
    - slitset positions inverted for offset and gap
    - nexus file: link names not nexus compliant
- Regulation framework
    - calling "stop" on loop only stops ramping, not regulation
    - better documentation
- Scans
    - Synchronization issues with data streams
    - cen, com and scan math functions greatly improved
    - measurement groups: Lima counters were all enabled when starting device server
    - Cannot dmesh two pseudo motors with number of scan points on each
    - Error in `goto_peak` with Calc Motor when the real motor is not in the session
    - better error message when a motor is used twice in the same multi-motors scan
- Shell
    - file descriptors not being cleaned up because of progress bar
    - user_scripts: command line completion works for function names, but not for arguments
    - blocking calls in gevent loop
- Tests
    - properly wait for Tango devices to be started
    - property wait for Tango DB to be started
- Tmux
    - one tmux server per session, one socket per tmux server

### Removed

- tmux context menu
- TCP_NODELAY option (Nagle algorithm for tinygrams) removed in Command object
- pixmaptools SIP extension
- posix_queue command line option for Beacon server startup script

## [1.5.0] - 2020-07-21

### Added
- event when Tango shutter state changes from BLISS 
- `reset_equipment` command in standard commands (bliss.common.standard)
- new `__info__` in motor group
- Mythen ROI counters
- hide methods starting with `_` in autocomplete in shell
- Taco client in bliss.comm
- new BackgroundCalcCounterController, to manage background for counters
- 'endproposal', 'enddataset' commands to manually stop an ICAT dataset
- 'reset()' command in Tango shutter
- new 'ladd' command to send output to logbook
- 'machinfo' object: new read-only properties to get storage ring current, and so on
- homing of Symetrie hexapod
- tmux option to change terminal window title
- protection of BLISS builtins in global dictionary
- Speedgoat motor controller
- generalized way to add dialogs for BLISS objects
- root path for data policy when using a LBS or BeGFS caching system
- dialogs for ascan, dscan, amesh, dmesh
- new features for axis jog move: change of velocity on-the-fly, jog_velocity property
- MUSST: timebase and memory info
- ISG shutter controller
- sync() error message now add name of the axis in case of problem
- Watchdog feature for scans
- Tolerance for pseudo-axes in NHQ power supply
- PM600: added flag to allow uploading of trajectory program only if needed
- Flint:
    - `flint()` command can be used to start Flint
    - Added API to start/stop monitorig on Lima
    - Added image plot GUI to custom live and exposure time while monitoring
    - Added export to logbook
    - Added extra markers to manually put in the plots
    - Added a window menu to change default docks visibility
    - Added tools to custom style and contrast of the scatters and images
      in the plot tool bar (and not only on the item property)
    - Update to silx 0.13
        - Provide cross profile for images and scatters
        - Provide extra profile tools for regular scatters to display data slice
          without interpolation
        - Provide histogram for scatters
        - Free line image profile for diffraction images
          (2 dedicated anchors for the start and a stop)
        - Added image colormap normalization: square-root, gamma, arcsinh
- sct: like ct but saves data by default

### Changed
- always display first master channel in F5 output
- user_script_load does not do backup anymore
- motor.position = X now displays a message for users with new position, offset
- CalcCounterController can use input/output counters specified in Python code
- remove counter group info from scan data table (F5)
- standardized OPIOM device communication configuration (YML)
- disable axis if autopower fails, without raising an error
- Flint:
    - Allow to select another curve when the fit dialog is open
    - Profile windows are now docks
    - Tune the scan status widget to resize the width smaller
  	- Provide tool to remove curves close to the y1/y2 indicators
	  - Rework the check of the flint API at startup to reduce pointless warnings
    - Group Lima ROI channels by ROI name in the property tree
- ct: 
    - ct as a default count time (1 second)
    - ct now works with count_time or counter as first argument.
      if count_time default value of 1s will be used.
    - ct does no longer allow to save data, use sct instead
    - ct does no longer collect metadata and positioners for scan_info
      this is to reduce the time cosumed by ct on top of the counting time
      in case positioners or metadata is needed, use `sct` instead.
    - ct (and sct) will no longer be added to SCANS queue of the session
- scan numbering: scans that are not saved use a shadow scan number and do not increase the scan numbers used in the hdf5 file.
- user_script:
    - `user_load_script` now exports to "user" namespace in session env dict by default.

### Fixed
- Axes
    - Geometry 8 of tab3 controller
    - axis group move exception and uninterruptible backlash issue
    - prevent communication with hardware if move is too small
    - motion hooks `_set_position` reset
    - sync_hard() no more raises an exception on disabled undulators
- Shell
    - incorrect SyntaxError in cells
    - function arguments completion in shell
    - doubling of entries in scan saving
- MUSST: fix for integrating counter read for any count time
- Lima
    - pilatus: internal trigger multi needs synch on trigger
    - ROI with 0 size
    - zombie threads when Lima bpm is used
    - 'acc_max_expo_time' not taken into account in default chain
- Scans
    - error in com calculation
    - rounding problem on goto_cen()
    - empty scan groups raising errors due to their state preset
    - scan numbers mixup
    - concurrent access issue in ScanSaving
    - exceptions happening during scan no longer shadowed by exceptions in presets
    - dnscan metadata
- ELMO controller: fixed abort command
- ACE controller: missing command to activate high voltage
- numpy array in Beacon object
- nanodac: target set position issue
- ASCII formatter for multi-bytes characters in output
- Icepap shutter support
- discrepancy error in icepap linked axis
- measurement group .enable/.disable commands on cameras with the same name prefix
- ParametersWardrobe reset command
- MCA
    - added logging
    - livetime => trigger_livetime
    - added energy_livetime
    - no default config bug
    - fix trigger mode and hwsca initialization
    - SYNC mode
    - msgpack error with XIA server 
- delay in commands to redis due to keys scan
- transfocator initialization 
- MOCO: fixed outbeam, added inbeam
- opiom: open program file from remote, initialization of boards with the right programs
- nanodac: target setpoint
- Wago:
    - fix negative values for thermocouples
    - WagoMotor adapted to work with Wago DS
    - key error when reading value, in case of concurrent access
- data streams:
    - fix missing priority when adding scan data stream
    - DataNode.get and block size fix
- Nexus Writer:
    - skip reference saving when paths are equal instead of checking existence
    - scans with save_images=False
- Flint
    - Fix wrong plot view with d2scan/d3scan
    - Fix replotting a scan using a single axis from 2 top master scan
- Web configuration application
    - distinguish measurement groups from sessions
    - save values with good type (not always strings)
    - find any config object in yml file
    - display 500 error

## [1.4.0] - 2020-05-18

### Added
- scan speed improvements
    - various optimization
    - use of hiredis for message packing/unpacking between BLISS and redis
- protection of global variables in BLISS shell
    - selected globals cannot be removed, or replaced (was asked during the last BLISS training at auditorium)
- "maxee" mode for axes with encoders
    - read of encoder position instead of motor controller position
    - various checks
    - added quadratic filtering capabilities to Encoder objects (used at ID11)
- helper to get channels from ScanPreset objects, in order to implement equipment protection for example
- helper to get acquisition devices from counters or axes (useful in Preset objects)
- Tango commands and attributes logging
    - allow to do "debugon(a_BLISS_device)" and to see all commands/attributes executed if a_BLISS_device talks to Tango
- refactoring of NHQ controller
- White Beam Attenuators with hooks on frontend + looking at home switches
- new flag to indicate a scan has been aborted
- messages when stopping motions
- saving comments in YAML files is now possible
- variables (not only constants) in expression-based calc counters
- added Lima debug in BLISS
- allow expression based CalcCounter to not have constants
- IcePAP: added methods _get_min_acceleration_time and _get_max_velocity
- Documentation:
    - Add regulation/temperature/powersupply
    - Add default chain and associated settings
- simulation for AutoFilter
- Nexus Writer:
    - added version to nexus files
- Flint:
    - API to select a mask image
    - Provide axis markers
- Allow to keep a reference to an object in Redis
- Speedgoat controller improvements

### Changed
- Shell
    - Flint will not be launched for CT without image or MCA
      despite `SCAN_DISPLAY.auto=True`
- updated documentation for data policy in BLISS
- 'ct' does not start Flint if counters are only 0D
- Lima dialogs more user friendly
- read-only variables in the shell
- improvement in DCM control (speedgoat, pepu, etc.)
- mca: move data reading loop on server side
- Documentation:
    - scan documentation update

### Fixed
- fixed bug in documentation pages generation and doc search
- PM600 controller bug fixes
- Moco counters do not show in measurement groups
- adapt EMH controller to new firmware
- fix of MCA simulator, after last changes which broke tests
- fixed usage of "pytest.approx" in tests
- 100% CPU load in clients when Beacon is stopped
- infinite recursion when setting value in axis from initialization method
- `is_moving property` of motor group object could report wrong value
- fix device.name in External Input/Output info
- show clear error message instead of traceback if BLISS needs to reconnect to redis
- limatake: added missing key in scan info
- fix bug on xia hwsca
- display error message if Beacon is not found, was not working with Tmux
- IcePAP: fixed acceleration time margin in trajectory mode
- Keithley: changed message for gain (0-10) -> (3-10)
- fix BeaconObject property_setting setter not working at first call
- tango_attr_as_counter: add missing initialization of conversion_factor
- `--debug` option enables ERROR_REPORT.expert_mode
- Resolve "GPIB timeout"
- Wago: fixed a bug for negative values on interlock representation
- fix Sharing motor between two sessions causing exception on initialzation
- NHQ Power Supply refactoring
- Nexus Writer:
    - skip reference saving when paths are equal
- fix on exception happening during scan can be shadowed by exception in
  scan preset

### Removed
- removed mx directory

## [1.3.0] - 2020-04-03

### Added

- CT2 (P201) controller
    - retries 5 times reading of point in case of error 
    - do not remove first point
    - change keep_first_point attribute by read_all_triggers and add it as a parameter for master and slave acquisition devices with default at 'False' to keep backward compatibility
- useful maths functions from numpy in bliss.shell.standard
- EBV controller now has BPM counters
- Nexus Writer
    - optimise Virtual Dataset creation by collapsing indices
- Axis
    - offset, backlash as writable properties for Axis objects
    - .dial_limits property
    - config changes are only taken into account when .apply_config is called
- Moco controller
- Lima image parameters: added binning
- web configuration tool: improvement of the search
- Axes DISABLED state is displayed in the output of `wa()`
- Undulators
    - wid() : "where insertion devices" display the list and status of undulators
    - added support for revolver undulators
- wait for refill
- A `plotinit` was added to request before a scan what it have to display.
    - It uses the same arguments as `plotselect`
    - This information is part of the scan then could be used by the writer
- Flint
    - The scan number is now displayed
    - Saved preferences for the main window can be difference for each desktop size used
    - Picking a point from the selected curve uses now a higher tolerance
    - A widget is displayed for ct scans
    - A widget can be shown to display scan positioners
      (location of the motors before and after a scan)
    - A past scan can be displayed in place of the curent scan
      (for curve widget, count widget, positioners widget)
    - A Spec mode was added to the curve widget, to display Spec-like
      statistics  

### Changed

- history files for tmux sessions or classic sessions are now the same
- umv, umvr now check parameters (using typeguard)
- `watch_session_scans` do not expose anymore scan_group as a scan
- `goto_cen` (and similar functions) displays first the marker, then move the motor
- Flint
    - On a new scan the plot selection is now more conservative
    - On a new scan if no previous selection, only a single counter is selected

### Fixed

- user_name in SCAN_SAVING and scan display
- user_local_script now raises an exception if invalid file is given, even in default session
- goto_cen and associated functions now work for calc axes
- config settings raise an exception if connection to Beacon is lost
- Axis
    - user and dial calculation for Axis when sign or steps per unit change in config
    - invalid backlash movement in case of floating point errors with position
- retrying and timeout to read metadata servers attributes
- scan or ct in default session when data policy is enabled
- Speedgoat
    - check number of counters to match buffers 
- where() with aliases
- channel .fullname returns the name with alias, if any
- keithley controller: fixed initialization trouble with the cache
- printing of config values for NoSettingsAxis
- serial line communication: open/close made atomic
- energy_wavelength calculation is compliant with numpy arrays
- dmesh: start, stop are calculated from the motor set position
- cleanup context manager: recorded motor position is set to the set position
- removed "encoder" prefix on Encoder counter names
- BLISS rpc
    - limit allocated memory for RPC messages on 32 bits computers 
- data stream
   - ensure a TTL of 60 seconds to the synchronization stream
- Nexus writer
    - stop scan when entry already exists in file
    - set dataRoot before starting the dataset
- `plotselect` now supports aliases
- Flint
    - Scans from a `ScanSequence` are now displayed (`ScanSequence` are ignored)
    - The view on the image widget is not anymore reset when a scan starting
    - The x-axis range when using a/dscan was now correct
    - The gaussian fit now also displays the FWHM in tooltips
    - The standard deviation computed from the gausian fit is now positive

### Removed

## [1.2.0] - 2020-03-01

### Added

- Encoder objects are now counter containers, to be used in scans
- __info__ strings for TCP, UDP, GPIB and Serial communication objects
- image information is returned by Lima Image __info__ method
- reload of Opiom program in multiplexer setup (only if needed)
- 'raw_read' property for Sampling Counters
- Transfocators
    - TFLens to manage number of lenses and different materials for each axis of the transfocator
    - setin(), setout()
    - take pinholes into account in total number of lenses
    - security checks when setting bitvalue
    - check for invalid state (both limits activated)
- EBV (Esrf Beam Viewer)
    - add counters list in __info__
- support for EMH controller
- support for Elettra BPM
- jog command for IcePAP controller
- Lima
    - add shutter property
    - BPM info return a list of bpm counters in one line
    - support for Mask, Background substration, Flat-field, binning, flipping, rotation
    - "limatake" tools
    - set instrument name and detector name
- Data policy
    - move positioners into separate scan_info category
    - new global 'instrument' field in configuration
- Introduction of Redis Streams to convey data from Beacon to clients
- Nexus Writer
    - adaptation to the new streams
    - creation of Virtual Dataset without re-opening image files
    - better profiling tools
    - improved performance
- Shell
    - lscnt can now take a counter or CounterContainer object, to limit output to this object
    - warn about tmux 'detach'
    - functions to load/execute user scripts: user
    - new lsmg: list measurement groups
    - edit_mg() method to edit measurement groups graphically
    - silx launcher: typing silx_view in the shell will launch silx on a scan (default last scan).
- Wago: 
  - support for special modules `750-403`, `750-506`, `750-507`, `750-508`, `750-637`
  - create an "extended_mode" (normally not used) to be able to retrieve all
    information from special modules (status, both input and output). 
    Activating this mode gives the capability to access those extra information, but
    could be not compatible with actual ISG protocol and with C++ device server.
  - `devreadphys` and `devreaddigi` will take values from a cache like is in C++
    device server, to get instantaneous values use `devreadnocachephys` and
    `devreadnocachedigi`. This can be used for monitoring without giving more
    pressure to the Wago. The shell command `get` gives instantaneous values.
- Flint
  - User choices on widget configuration are now stored in Redis
  - Create `clean_up_user_data` function in BLISS side (`bliss.common.plot`)
    to be able to clean up Redis from Flint corrupted data in case of problem.
  - A preferred style can be saved as default for images
  - `plotselect(diode2)` can now be used if the scan is already displayed
  - `SCAN_DISPLAY.init_next_scan_meta(display=[diode2])` can be used just before
    scanning
  - Provide layout menu to allow to setup predefined layouts
  - Provide menu to lock/unlock the layout (by default the layout is locked)
  - Provide workspace to be able to store plot, widget, layout in different environment
  - The image widget displayed now the source of the data (can be "video", "file", "memory")
- APC Rack Power Distribution Unit: implemented controller for basic relay functionalities
- BLISS RPC: new low latency messages
- Documentation
  - "BLISS in a nutshell": interactive tutorial
  - documentation day: many updates
- BLISS demo session

### Changed

- Scans
  - disable all 'lprint' messages while scan is running
- Flint
  - Use silx 0.13.0 beta0
  - Rework image/MCA/curve live view in order to provide same behavior as scatter view
    - Cleaned up toolbar
    - Cleaned up tooltips
    - Manage data display according
  - Do not allow anymore to display more than one image in the image view
  - Image and scatter autoscale can use auto based on standard deviation
  - Display curve live view x-axis with timeseries if the channel unit is "s"
  - Cut channels data at the end of timescan scans to enforce the same size
    - It's a workaround, but can be used for other default scan if requested
  - The layout is now stored into the Redis session
  - All MCAs (or images) from a device are displayed inside a single widget
    - This widget is named according to the device name (preciselly the prefix
      of the channel name)
  - At the start of a scan, the previous image is still displaed to avoid blinking
  - Image from Lima is downloaded according to the user refresh rate choice
- moved Linkam, Lakeshore to the regulation framework 
- CT2 (P201): send data from the server instead of doing polling on client
- Data policy
    - enforcing server names

### Fixed

- EBV counters property
- Counting on individual calc counters
- Aliases (motor or counter) display bug solved (see #1234)
- Web configuration tool
    - do not open editor for binary files
    - do not hide buttons while scrolling
    - toggle folder open/close icon
    - hide TODO message for objects without UI
- BLISS TANGO Axis logging activation with command line flag (-v1..4)
- lprint_disable context manager
- Elmo motor controller
    - fixed jog, encoder, homing
- Fix environment dictionary in case of nested sessions
- CT2 (P201) counter values conversion
- Software timer elapsed time

### Removed

## [1.1.0] - 2020-01-15

### Added

- Beacon:
  - Log Server: all log messages (plus exceptions and user input) are sent to a socket server
                that can be started with Beacon, this will save to a Log Rotating File
                on a selected folder (default to `/var/log/bliss`).
  - Log Viewer: a logging viewer web application process can be started to serve on a selected
                http port (default 9080) on the Beacon Host
- last_error: now contains the last 100 exceptions that can be accessed with list notation
              last_error[-1] for the last one.
- conversion_function can now be set at runtime on Counter objects
- support for Cyberstar powersupply
- __info__ method for opiom, mca, ebv, emh, measurement groups, wba, multiple position objects, hexapod, vscanner, Keithley, shutters
- setting motor position now display a message to user
- first version of the Nexus writer Tango server
- Transfocators fill metadata
- Tango attribute as counter: added .value and .raw_value to read the attribute out of a scan context

### Changed

- Flint
  - Update silx to the last 0.12
  - Rework live scatter plot
    - Style and min/max range can be customized by the user
    - A preferred style can be saved as default
    - New rendering provided (image-like solid rendering)
    - Toolbar reworked
    - Behaviour of "reset zoom" reworked (this will be used for other plots)
  - Improve the mouse data picking
    - Mechanism provided to setup the view at startup on the full range of the x/y axis
    - This feature is provided for `amesh` and `dmesh`
    - To implement if on your scans take a look at https://bliss.gitlab-pages.esrf.fr/bliss/master/flint_scan_info.html
- web applications (configuration, homepage and log viewer) are now started by default
    - default port numbers are proposed

### Fixed

- Beacon web configuration:
  - Fixed "Revert" of the editor content
  - Some ergonomic improvements (ctrl-s to save the editor, css styles)
- typeguard version set to 2.6.1 instead of 2.7
- info() now works for classes and types
- Wago
    - interlocks
    - support for CPU model 750-891
    - 0-10V overflow and negative voltage
    - MissingFirmware exception
    - numpy types
- {scan_number} and {scan_name} bug in ScanSaving is fixed
- call prepare_scan_meta after writer template has been updated
- fix file descriptors leakage
    - new gevent-friendly Redis connection pool
    - Tango connections cleaning (in tests)
    - gevent patch to ensure hubs are closed when threads get destroyed
- fix asynchronicity problems and race conditions in Beacon server and client code
- multiple Beacon objects with the same name are now properly initialized  
- bug in AllowKill context manager

### Removed

## [1.0.0] - 2019-12-17

### Added

- Controllers
  - Hardware SCA mode for Xia Mercury
  - Interlocks support for Wago
  - WagoGroup, to group multiple Wagos in one
    - Tango Wago server using BLISS controller
  - PM600 trajectories
  - PI-E517 specific improvements
  - use home_src for Icepap "home()" method

- Configuration
  - '.' can now be used directly access attributes of referenced objects
  
- Scanning toolbox
  - `ChainBuilder` class: helper to build a custom scan with auto-introspection of the counters dependencies given to a scan.
  - `ChainNode` class: used by the `ChainBuilder` to store required information about the links between Counters, CounterControllers and AcquisitionObjects.

- CounterController
  - New file `bliss.controllers.counter` including the base classes of the standard CounterControllers:
    - `CounterController` base class for `Counter` management.
    - `SamplingCounterController` class for `SamplingCounter` management.
    - `IntegratingCounterController` class for `IntegratingCounter` management.
    - `CalcCounterController` class for `CalcCounter` management.
      - can deal with N input counters, and produces M output counters
    - `SoftCounterController` class for `SoftCounter` management.

- AcquisitionObject
  - New `AcquisitionObject` base class for `AcquisitionSlave` and `AcquisitionMaster` (`bliss.scanning.chain`).
  - Validation of acquisition object parameters using Cerberus

- Scans
  - add '.wait_state()' method to help with the synchronization of states
  - grouping feature

- Regulation framework
  - new module `bliss.common.regulation` to manage PID regulation of various systems.
  - new `SoftLoop` object that implements a software PID regulation algorithm.
  - new `ExternalInput` and `ExternalOutput` objects in order to transform any devices into an `Input` or `Output` for a the `SoftLoop` regulation.

- Session
  - Store scans in `.scans` property in `Session` object.
  - Scan saving structure available in `Session` object (.scan_saving).
  
- Flint
  - Provides dock widget for all the main widgets of the live scan window
  - Provides a widget to monitor the state of the current scan
  - Provides a single 'property' widget to configure the live plots
  - Provides new widgets for curves, scatter, images, MCAs (it is supposed to provide more or less the same features)
  - Curve widget supports many master (a curve can only be created from 2 channels of the same top master)
  - A IPython dialog is provided in the Help menu
  - Location of the docks are saved between 2 executions of the application (local computer user preferences)
  - Improve autodetection of the plot and axes according to the kind of scans
  - Display the frame id for images
  - Experimental
    - Many MCAs can be displayed on the same plot
    - Many scatters (sharing the same axis) can be displayed on the same plot
    - Many images can be displayed on the same plot. The first one is displayed as an image, others as scatter
  - `SCAN_DIPSLAY.extra_args` was added to custom command line argument passed to flint
    - `--enable-opengl` to use OpenGL rendering for plots (it should provide faster rendering, but could have issue with remote desktop)
    - `--enable-gevent-poll` to use experimental patching of poll system function for a better cooperative between Qt and gevent (it should reduce CPU consumption but could be unstable)
    - `--matplotlib-dpi DPI` to custom the plot DPI (this setting will be stored in the local user preferences)
    - `--clear-settings` to allow to start with cleared previous local user settings
  - Flint stdout/strerr are logged inside bliss `flint.output` logger
    - This logger is disabled by default
    - The output is retrived from both created or attched Flint process
    - `SCAN_DIPSLAY.flint_output_enabled` allow to enable/disable this logger
  - Custom plots can be created with `selected=True` and `closeable=True`
  - 2 scripts was added to optimize and convert SVG to PNG
    - `scripts/export_svg.sh`, `scripts/optimize_svg.sh`

- Typing Helper
  - pressing F7 will disable typing helper on Bliss Shell
  - avoid interpretation of multiline code and of properties

- Shell
    - start Flint in shell only
    - clear() function to clear screen

- Logging
    - lprint: new function intended to replace print for printing to stdout and to log file

- Scan saving
    - new Nexus Writer Service
  
### Changed

- Measurement groups
  - configuration specify which counters or controllers (counter containers) can be used by a measurement group  
  - individual ounters to be enabled or disabled are selected using the Unix "glob" pattern (*, ?, [..])
  - entire counter groups can be enabled or disabled

- Scans
  - Scan saving '.get()' do not create redis node
    - node creation is done in the run method of Scan
  
- Counters refactoring
  - The file `bliss.common.measurement` has been renamed `bliss.common.counter`.
  - Unique base class `Counter` (`bliss.common.counter`) for counters objects.
  - The `Counter` object requires a `CounterController` object (`bliss.controllers.counter`) (mandatory).
  - The `Counter` object has a `._counter_controller` property which returns its `CounterController` (the counter owner).
  - All standard counters (`SamplingCounter`,`IntegratingCounter` ,`SoftCounter` , `CalcCounter`) inherit from the `Counter` base class.
  - counter classes defined in the same file as corresponding controllers

- CounterController
  - The file `bliss.controllers.acquisition` has been renamed `bliss.controllers.counter`.
  - `get_acquisition_object` method attached to the `CounterController` object.
  - `get_default_chain_parameters` method attached to the `CounterController` object.

- AcquisitionObject
  - `AcquisitionSlave` inherits from `AcquisitionObject` base class.
  - `Acquisitionmaster` inherits from `AcquisitionObject` base class.

- Flint
  - Default curve colors was updated
  - `bliss.scanning.Scan.get_plot` API was changed, now it uses a channel object and a plot kind (`image`, `scatter`, `mca` or `curve`)
    - This API is only used by `edit_roi_counters` and will may be removed
  - Try to avoid to reach images which are not needed (according to the frame id already reached)
  - `selectplot` do not anymore set the default displayed channels in the plot (temporary regression)

- Globals
  - `SCANS` is now available only in Bliss Shell. Refers to `current_session.scans`
  - `SCAN_SAVING` is now available only in Bliss Shell. Refers to `current_session.scan_saving`

- Command line arguments
  - `--tmux-debug` command line option changed to only `--debug`

- bliss.common.standard
  - this module is intended to be the entry point for Bliss as a library, function that
    were printing to stdout has been changed to return some forms of aggregated data
  - function to be used inside the Bliss shell (with print to stdout) are moved to bliss.shell.standard

### Fixed

- Flint
  - Location of the live plots stay the same between 2 scans
- Fixed wrong call to 'atan' instead of 'arctan' in QSys calc motor and tab3 controller
- Fix BPM counter group for new Lima BPM device
- Stop live mode when calculating BPM
- Add Lua script to do atomic updates of Setting objects
- CT2: take device name into account to generate the data channel name
- Icepap: do not initialize axis in Switch
- Fix for Lakeshore controller initialization
- Fix missing SCANS global in BLISS shell in case of error during setup
- Fix to take image save flag into account for the Null writer
- Display SoftAxis motors in wa()
- Conversion function property added to SoftCounter
- Fix Aerotech encoder reading
- Fix oscillating movement on repeated Icepap limit search
- SSI encoder reading support for Wago
- Group move now stops if one of the moving axis is stopped individually
- Motor group ".move()" do not accept numpy arrays anymore
- Fix external shutter switch enum
- Show axis position marker in Flint for goto_cen, goto_peak, goto_com functions
- Deleting a node in global map do not reparent
- Display exception in `__info__` methods
- Watchdog timer restart logic

### Removed

- Counters refactoring
  - `BaseCounter` interface class has been removed.
  - `GroupedReadMixin` class has been removed.
  - `controller` property removed from the `Counter` class.
  - `master_controller` property removed from the `Counter` class.
  - `create_acquisition_device` method removed from the `Counter` class.
  - `DefaultSamplingCounterGroupedReadHandler` has been removed.
  - `DefaultSingleSamplingCounterReadHandler` has been removed.
  - `DefaultIntegratingCounterGroupedReadHandler` has been removed.
  - `DefaultSingleIntegratingCounterReadHandler` has been removed.
  - `Read` method removed from `SamplingCounter` class.

- AcquisitionObject
  - `AcquisitionDevice` renamed as `AcquisitionSlave`.

- Flint
  - `flint.set_dpi` was removed. A local use setting is provided now.
  - Redis node `SESSION:plot_select` is not anymore updated by the GUI
  - Redis node `SESSION:scatter_select` is not anymore updated by the GUI
- `bliss.common.plot.BasePlot.clear_selections` was removed

- Scans
  - duration estimation is no longer provide, since it cannot be calculated accurately

## [0.3.0] - 2019-10-01

### Added

- Controllers:
  - Added EMH Alba electrometer
  - Added ESRF Hexapode
  - Musst patch: add capability of using a template replacement when loading Musst software into controller
  - Lima patch: Sebastien
- Acquisition Chain:
  - Allow to add only one master (without the slave) in an acquisition chain
- Scan:
  - Watchdog Feature: it is possible to add a callback to a scan
    using **set_watchdog_callback** method and passing a subclass of
    bliss.scanning.scan.WatchdogCallback. This allows to check the behaviour of
    detectors involved in the scan and eventually raise an exception.
    The following callbacks can be defined: on_timeout, on_scan_new, on_scan_data, on_scan_end (#946)
- Bench context manager: helper to measure execution time of any given code. (#861)
- timedisplay: visualize time values in human readable form

### Changed

- Scan:
  - All common step scans command take now **intervals** instead of **npoints**. (#931)

### Fixed

- Controllers:
  - opium always reload the program (#987)
  - icepap: load trajectory axes by block
  - Aerotech: added AeroTechEncoder class to properly handle encoder steps
  - MultiplePosition: resolved move(wait=False) never sends READY event (#1001)
  - energywavelength: bug fix and test
- logging: exposed debugon/off on the shell standard commands (#986)
- lima interface: Force the plugin name to be lower case for compatibility
- motion hooks: axis objects are not initialized in 'add_axis()' (#1002)
- return of DataNode.get is convertible into a numpy array (#1007)
- fix synchronization problem in external writer (#993 #992)
- fix data listener: protect from any exception
- make sure that name of node does not change after node creation (#1003)
- changed calculation of horizontal offset for slits (#1009)
- louie conda package for windows (#1011)
- Resolve Lima files when SCAN_SAVING.writer == 'null' (#1010)
- Flint:
  - Fixes curve widget autoscale when selecting/switching y1/y2
  - Fixes image widget display when the image channel is a master

### Removed

- New controllers support added:
  - esrf_hexapode controller

- Bliss Shell
  - **info(obj)** function will standardize the representation of an object inside Bliss shell,
    it uses underline `__info__` method if it exists and eventually falling back to `repr`

## [0.2.0] - 2019-08-23

### Added

- Bliss Shell Interface
  - New Bliss interface for visualize Scan results on a different window (pressing F5).
    It uses Tmux under the hood allowing a bunch of new capabilities like remote assistance (replacing the need of `screen`)
    Launching Bliss will use Tmux as a default, use the `--no-tmux` option to start a session without tmux
  - New UserDialogs available to interact with users (ask questions and display messages)
- Bliss Shell
  - Exception Management
    - more friendly exception management hiding exception details under `last_error` global variable (#402)
    - Introduced global variable ERROR_REPORT.expert_mode to allow full traceback for expert users
  - added `history` tooltip for viewing last commands (globals)
  - add shell autocompletion for dynamic attributes
- New controllers support added:
  - Aerotech Soloist
  - Elmo whistle
  - Lakeshore 331/332/335/336/340
  - MultiplePositions
  - Mythen/Mythen2
- Counters
  - Soft Timer provides also `epoch` time (before was only delta)
  - Added simulation_counter for user testing purposes
  - Calculation counter can now be defined over other counters
  - Tango Attribute counter can now use `unit` and `display unit` from Tango config
  - Sampling counter modes statistics
- Now is possible to iterate Counters and Motors
- Sessions
  - A Bliss Session will connect to an existing one if they share the same name and host.
    In fact the same session will have only one instance at a time. This assumes underline use of Tmux
- Aliases
  - shortcut for bliss objects (Axis, Counters, Channels) at a session level
  - used in hdf5
  - global ALIASES
- Global Map
  - New Session map where controllers/connections/aliases/counters are registered when they are
    loaded. Provides convenient runtime access to all instances and allows building on
    top other services.
  - Comes with visualization capabilities useful for debug or other purposes.
- Logging
  - Based on Global Map it allows to log each individual instance of the same class of
    controller/connection.
  - Rich set of shell commands: lslog, log_debug, debugon, ...
- GitLab continuous integration
  - test is skip if only docs are changed
  - allow graphical tests
  - new coverage report
  - package building for tagged version (releases)
- Beacon Config
  - Config
    - order of element in file is now keeped while saving (instead of sorted)
  - new BeaconObject that groups Static Configs and Settings, to be used when planning to
    use both Config and Settings
- Scan
  - New `pointscan` that performs scan on a list of positions
  - New ScanPreset argument to perform operation on prepare/start/stop
  - Alligment with multiple motors can be done propertly with (cen, com, peak, ...)
  - New possibility to add further metadata when launching a Scan using scan_meta
- hdf5
  - Values of underline Calculation Motors are exported
  - Documentation about external data writing script
- SamplingModes refactor with new modes: STATS, SAMPLES, SINGLE, LAST, INTEGRATE_STATS
- flint new possibility to select any (X,Y) axis combination for plot
- IntegratingCounter: master_controller can now be None

### Changed

- controllers: py2to3 porting, improvements, refactor and bugfix
  - Add commands for keithley 6514 and 2000
  - Icepap
    - Change of names
    - API change in linked axis
    - New `show` command to check enabled/disabled axis
    - New check of trajectory number of points in regard to Icepap memory
  - Euro2400
  - Keithley 485
  - Lakeshore
  - Musst
  - Md2
  - pi_c663
  - pi_e712
  - pi_e727
  - pi_e871
  - pi_hexa
  - Prologix
  - Scpi
  - Shexapod v1 and v2
- Web interface py2to3 port
- Parameters renamed in ParametersWardrobe with improved functionalities:
  - allow export to YAML file and beacon
  - allow property_attributes (read-only) and not-removable parameters
  - add purge, remove, copy, freeze, show_table
- SamplingModes refactor with renaming of SIMPLE_AVERAGE to MEAN

### Fixed

- musst: python3 data reading, synchronization
- "Add WagoAirHook hook" (#772 #110)
- Static config: simplify reparent process (#495)
- fuelcell: "import of fuelcell (moved to id31 dir.) (#817)
- hdf5: "writer try to create an existing scan entry" (#620)
- shell:
  - "Line numbering does not increase in bliss shell" (#610)
  - "Exit shell with \<CTRL-d> + return"
  - "Deprecation warning coming from jinja2" (#688)
  - ".counters namespace not accessible from command line" (#625)
  - "kwargs in signature display in shell" (#798)
  - "typinghelper check callable " (#746)
- gevent: "gevent timeout"
- gitlab CI:
  - "do not copy htmlcov dir to public/"
  - "added missing libxi6"
- gpib: "ibwrt python3 tango" (#574)
- scan:
  - "scan preset" (#561)
  - "Scan display: does not work when multiple points are received at the same time" (#743)
  - "Scan listener missing output lines on fast scan" (#747)
  - "real motors of nested calc axis not published" (#714)
  - "scan.run should raise an exception if re-started" (#771)
  - "empty .children() list of data note after NEW_CHILD" (#826)
- web interface: "web page interface" (#627)
- louie: Remove louie from StepScanDataWatchCallback (#645)
- rpc: "uds connection when the socket is removed, return AttributeError"
- fix on node __internal_walk
- serial: "use url if port is not set"
- redis:
  - "fullnames containing : and ." (#615)
  - "exception in TTL setter" (#630)
- "really use alias name in session" (#700)
- flint/silx:
  - "axes colors" (#717)
  - "rulers are not updated" (#718)
  - "error in Flint interaction" (#829)
- "Throwing an error in channel notification breaks object" (#719)
- "apply_config() fails if wrong settings have been set at first init" (#751)
- "double definition of close" (#587)
- "Load_scripts does not return an object or function" (#722)
- lima:
  - "fix missing .fullname in Lima data node object"
  - "fix of lima bpm simulator working again" (#664)
- "YAML 1.1 specification says ON, OFF, and other values should be converted to boolean" (#781)
- "BaseShutter `repr` bug" (#783)
- "motor is not initialized with MOVING state in axis settings"
- "comm.tcp.Command.connect : undefined variables" (#824)
- "prdef does not print correctly the inspected function" (#777)
- "Cannot set unit on tango_attr_as_counter" (#833)  
- "Saving/Editing configuration implemented in a controller" (#835)
- "lima: fixed timescan" (#844)
- "manage limits always in DIAL. convert limits only on user interaction" (#854)

### Removed

## [0.1.3] - 2019-03-07
