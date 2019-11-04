# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Session
  - Store scans in `.scans` property in `Session` object.
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
  - 2 scripts was added to optimize and convert SVG to PNG
    - `scripts/export_svg.sh`, `scripts/optimize_svg.sh`
  - Typing Helper
  - pressing F7 will disable typing helper on Bliss Shell
  - avoid interpretation of multiline code and of properties

### Changed

- Flint
  - Default curve colors was updated
  - `bliss.scanning.Scan.get_plot` API was changed, now it uses a channel object and a plot kind (`image`, `scatter`, `mca` or `curve`)
    - This API is only used by `edit_roi_counters` and will may be removed
  - Try to avoid to reach images which are not needed (according to the frame id already reached)
  - `selectplot` do not anymore set the default displayed channels in the plot (temporary regression)
- Globals
  - `SCANS` is now available only in Bliss Shell. Refers to `current_session.scans`
  - `SCAN_SAVING` is now available only in Bliss Shell. Refers to `current_session.scan_saving`

### Fixed

- Flint
  - Location of the live plots stay the same between 2 scans

### Removed

- Flint
  - `flint.set_dpi` was removed. A local use setting is provided now.
  - Redis node `SESSION:plot_select` is not anymore updated by the GUI
  - Redis node `SESSION:scatter_select` is not anymore updated by the GUI

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
