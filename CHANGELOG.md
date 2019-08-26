# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2019-09-23
### Added
- Bliss Shell Interface
  - New Bliss interface for visualize Scan results on a different window (pressing F5). 
    It uses Tmux under the hood allowing a bunch of new capabilities like remote assistance (replacing the need of `screen`).
    Launching Bliss will use Tmux as a default, use the `--no-tmux` option to start a session without tmux.
    - New UserDialogs available to interact with users (ask questions and display messages)
- Bliss Shell
  - Exception Management
      - more friendly exception management hiding exception details under `last_error` global variable.
      - Introduced global variable ERROR_REPORT.expert_mode to allow full traceback for expert users
  - added `history` tooltip for viewing last commands (globals)
  - add shell autocomplexion for dynamic attributes
  - **info(obj)** function will standardize the representation of an object inside Bliss shell,
    it uses underline `__info__` method if it exists and eventually falling back to `repr`.
- New controllers support added:
  - Aerotech Soloist
  - Elmo whistle
  - Lakeshore 331/332/335/336/340
  - MultiplePositions
  - Mythen/Mythen2
- Counters:
  - Soft Timer provides also `epoch` time (before was only delta)
  - Added simulation_counter for user testing purposes
  - Calculation counter can now be defined over other counters
  - Tango Attribute counter can now use `unit` and `display unit` from Tango config
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
    use both Config and Settings.
- Scan
  - New `pointscan` that performs scan on a list of positions
  - New ScanPreset argument to perform operation on prepare/start/stop
  - Alligment with multiple motors can be done propertly with (cen, com, peak, ...)
  - New possibility to add further metadata when launching a Scan using scan_meta
- hdf5
  - Values of underline Calculation Motors are exported
  - Documentation about external data writing script
- SamplingModes refactor with new modes: STATS, SAMPLES, SINGLE, LAST, INTEGRATE_STATS

### Changed
- Controllers: py2to3 porting, improvements, refactor and bugfix
  - Add commands for keithley 6514 and 2000
  - Icepap
    - Change of names
    - API change in linked axi
    - New `show` command to check enabled/disabled axis
    - New check of trajectory number of points in regard to Icepap memory
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

### Removed


## [0.1.3] - 2019-03-07
