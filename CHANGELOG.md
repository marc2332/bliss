# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
  - add shell autocomplexion for dynamic attributes
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
  - "Exit shell with <CTRL-d> + return"
  - "Deprecation warning coming from jinja2" (#688)
  - ".counters namespace not accesible from command line" (#625)
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
- rpc: "uds connection when the socket is removed, return AttributError"
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
- "motor is not initialised with MOVING state in axis settings"
- "comm.tcp.Command.connect : undefined variables" (#824)
- "prdef does not print correctly the inspected function" (#777)
- "Cannot set unit on tango_attr_as_counter" (#833)  
- "Saving/Editing configuration implemented in a controller" (#835)
- "lima: fixed timescan" (#844)
- "manage limits always in DIAL. convert limits only on user interaction" (#854)


### Removed


## [0.1.3] - 2019-03-07
