# BLISS sessions


## BLISS session

A *Session* groups BLISS objects defined in configuration under a single entity.

Such a group can reflect geographic characteristics (ex: *all devices of EH1*)
or functional characteristics (ex: *Spectrometers motors and counters*)

By default, *all objects* defined in beacon configuration will be loaded, then
the setup file is executed. To load only specific objects, the *YAML
configuration file* of the session must be adapted.

The *setup file* associated to a session is a Python script that is executed
after session objects are created. It can load user scripts and execute
user-defined functions.


## Launching a BLISS session

A session can be started in the *BLISS shell command line* with `-s` option:

```
% bliss -s eh1
```

```python
                       __         __   __
                      |__) |   | /__` /__`
                      |__) |__ | .__/ .__/


Welcome to BLISS version 0.02 running on pcsht (in bliss Conda environment)
Copyright (c) 2015-2020 Beamline Control Unit, ESRF
-
Connected to Beacon server on lid421 (port 3412)
eh1: Executing setup...
Initializing 'pzth'
Initializing 'simul_mca'
Initializing 'pzth_enc'
Hello eh1 session !!
Done.

EH1 [1]:
```


!!! note
    Two identical sessions cannot be started in a BLISS shell. This is
    ensured by usage of *Tmux* and by a locking mechanim. Tmux will display the
    previously started session instead of re-starting a new one. If Tmux is not
    used, an error message from the locking mechanism should appear at the
    second start of `demo` session:
    
    `demo is already running on host:pcsht,pid:8825 cmd: **bliss -s demo**`
    
    The error message gives all info needed to find where is running the previously
    started session and to deal with it (to kill it or to keep it).



## Files organization

The files used to configure a session are located in
`~/local/beamline_configuration/sessions/` directory.

```
 ~/local/beamline_configuration/
   ├── ...
   ├── sessions/
   .   ├── eh1.yml           <---- session configuration file
   .   ├── eh1_setup.py      <---- session setup file
       ├── __init__.yml
       └── scripts/
           ├── eh1_utils.py  <---- eh1 session related scripts
           |...
```


!!! note
    `__init__.yml` file contains `plugin: session` ; then, all YAML files in the
    directory are loaded using the Session plugin.


##  YAML Session configuration file

The file `~/local/beamline_configuration/sessions/<session_name>.yml` is used to
define for a session:

* the name of the session
* a list of objects to include or not in this session
* a list of measurment groups to include or not in this session

```yaml
- class: Session
  name: eh1
  setup-file: ./eh1_setup.py
  ...
```

The file `eh1.yml` defines a session called `eh1`, with a `eh1_setup.py` setup
file.

!! note
    The file path is relative to the session YAML file location if it starts
    with `./`, otherwise it is absolute from the root of the Beacon file database.

By default, **all objects** defined in the configuration will be loaded in the
session. It is possible to specify which objects must be included or not by
using the `config-objects` keyword with the list of object names:

```yaml
    - class: Session
      name: eh1
      setup-file: ./eh1_setup.py
      config-objects: [pzth, simul_mca]
```

The list of objects can also be written as:
```yaml
    - class: Session
      name: eh1
      setup-file: ./eh1_setup.py
      config-objects:
        - pzth
        - simul_mca
```

Conversely, `exclude-objects` can be used to *not load* unused objects.


!!! note
    Sessions **can be nested** using `include-sessions`. This allows to have a
    session for a specific equipment, for example, and to be able to include
    the whole equipment and its setup in another session.


## Setup file

The *setup file* associated to a session (usualy
`~/local/beamline_configuration/sessions/<session_name>_setup.py`) is a Python
script that is executed after session objects are created.

All objects from the session are available in the setup script. The *globals*
defined in the setup script, and all session objects, are automatically added to
the `bliss.setup_globals` namespace, to be used in user scripts.

```py
import os
from bliss.common.standard import * # import all default functions, scans, etc.

SCAN_SAVING.base_path = os.path.join(os.environ["HOME"], "scans")
SCAN_SAVING.template = "{session}/{date}"
print "Setting scanfile to", SCAN_SAVING.get_path()
```

All objects can be made available in the session with:

```python
from bliss.setup_globals import *
```


## User scripts

Python files defined under the special `scripts/` directory can be loaded in the
setup file of a bliss session using the `load_script(<file_name>)` function.

All commands in the file are then executed.

In case of error, the `load_script()` function catches and displays exceptions,
but do not prevent the rest of the setup from executing. Each call to
`load_script` re-execute the commands again.

`load_script` is the equivalent of the `execfile` Python function, but for
session scripts.

!!! note
    
    User script located in session directory should be session-specific.
    
    Beamline specific should be placed in another directory to ease their maintenance.
    see: https://bliss.gitlab-pages.esrf.fr/ansible/local_code.html

### Example

The file is: `~/local/beamline_configuration/sessions/scripts/demo.py`

```python

import time
# 'time' module is now usable in this file, but also in the session
# 'demo' after loading of the script.

print("[loading script]: align_spectrometer()")

def align_spectrometer(energy=5.0):
    print(f"Aligning spectrometer for energy {energy}...")
    time.sleep(1)
    print(f"Spectrometer is aligned :)")
```


Example of script loading and usage:

```python
DEMO [1]: load_script('demo')
[loading script]: align_spectrometer()
DEMO [2]:
DEMO [2]: align_spectrometer(energy=7.5)
Aligning spectrometer for energy 7.5  ...
Spectrometer is aligned :)
DEMO [3]:
```


## Automatic session creation

A skeleton of BLISS session can be created automatically with the `-c` option:

example for a session named `demo_session`
```
(bliss) pcsht:~ % bliss -c demo_session
Creating 'demo_session' BLISS session
Creating sessions/demo_session.yml
Creating sessions/demo_session_setup.py
Creating sessions/scripts/demo_session.py
```

At start-up, the new session will display a message to help customization:

```
% bliss -c demo_session
[...]
Welcome to your new 'demo_session' BLISS session !!
You can now customize your 'demo_session' session by changing files:
   * .../demo_session_setup.py
   * .../demo_session.yml
   * .../scripts/demo_session.py
```


If a session already exists, it will not be erased or reset.

```
% bliss -c demo
Session 'demo' cannot be created: it already exists.
```

A session can be deleted with the `-d` option:

```
% bliss -d demo_session
Removing 'demo_session' session.
removing .../sessions/demo_session_setup.py
removing .../sessions/demo_session.yml
removing .../sessions/scripts/demo_session.py
```
