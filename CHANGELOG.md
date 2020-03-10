# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Flint
    - The scan number is now displayed
    - Saved preferences for the main window can be difference for each desktop size used
    - Picking a point from the selected curve uses now a higher tolerance

### Changed

- `goto_cen` (and similar functions) displays first the marker, then move the motor

### Fixed

- Flint
    - The view on the image widget is not anymore reset when a scan starting
    - The x-axis range when using a/dscan was now correct
    - The gaussian fit now also displays the FWHM in tooltips
    - The sandard deviation computed from the gausian fit is now positive

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
