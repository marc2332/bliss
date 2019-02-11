# BLISS sessions

## Session configuration

A *Session* groups objects from configuration under a single name.
A setup file can be associated with the session. The setup file is a
Python script, that is executed after session objects are created.
The setup file can load user scripts, that are exposed to the global
namespace.

### Files organization
    .
    |── ...
    ├── sessions
        ├── id232.yml
        ├── id232_setup.py
        ├── __init__.yml
        └── scripts
            ├── beam_size.py
            |...

`__init__.yml` contains `plugin: session` ; then, all YAML files in
the directory are loaded using the Session plugin.

!!! note
    `scripts` is a special directory, that needs to be put under a Session
    object parent directory for the `load_script()` function to be able
    to find the scripts

### Example session YAML file

```yaml
- class: Session
  name: id23-2
  setup-file: ./id232_setup.py
```

`id232.yml` defines a session called `id23-2`, with a `id232_setup.py` setup file.
The file path is relative to the session YAML file location if it starts with `./`,
otherwise it is absolute from the root of the Beacon file database.

By default, **all objects** defined in the configuration will be
loaded in the session.  It is possible to specify which objects must
be included or not by using the `config-objects` keyword with the list
of object names:

```yaml
    - class: Session
      name: eh1
      setup-file: ./eh1_setup.py
      config-objects: [pzth, simul_mca]
```

Conversely, `exclude-objects` can be used to avoid to load unused objects.

Sessions **can be nested** using `include-sessions`. This allows to have a
session for a specific equipment, for example, and to be able to include
the whole equipment and its setup in another session.

### Setup file example

```py
import os
from bliss.common.standard import * # import all default functions, scans, etc.

SCAN_SAVING.base_path = os.path.join(os.environ["HOME"], "scans")
SCAN_SAVING.template = "{session}/{date}"
print "Setting scanfile to", SCAN_SAVING.get_path()
```

All objects from the session are available in the setup script. The
globals defined in the setup script, and all session objects, are
automatically added to the `bliss.setup_globals` namespace, to be used
in user scripts.

### User scripts

Python files defined under a session `script` directory can be loaded
in the setup file using the `load_script('script_name')` function. In
case of error, the function catches and display exceptions, but do not
prevent the rest of the setup from executing. Each call to
`load_script` reloads the Python script again.  `load_script` is the
equivalent of the `execfile` Python function, but for session scripts.

## Launching a BLISS session

A session can be started on the BLISS shell command line with `-s` option:

    % bliss -s eh1
                           __         __   __
                          |__) |   | /__` /__`
                          |__) |__ | .__/ .__/


    Welcome to BLISS version 0.02 running on pcsht (in bliss Conda environment)
    Copyright (c) ESRF, 2015-2018
    -
    Connected to Beacon server on pcsht (port 3412)
    eh1: Executing setup...
    Initializing 'pzth'
    Initializing 'simul_mca'
    Initializing 'pzth_enc'
    Hello eh1 session !!
    Done.

    EH1 [1]:

**All objects** defined in beacon configuration will be loaded, then the setup
file is executed.

## Automatic session creation

A skeleton of BLISS session can be created automatically with the `-c` option:

    (bliss) pcsht:~ % bliss -c docsession
    Creating 'docsession' BLISS session
    Creating sessions/docsession.yml
    Creating sessions/docsession_setup.py
    Creating sessions/scripts/docsession.py

At start-up, the new session will display a message to help customization:

    % bliss -c docsession
    [...]
    Welcome to your new 'docsession' BLISS session !!
    You can now customize your 'docsession' session by changing files:
       * /docsession_setup.py
       * /docsession.yml
       * /scripts/docsession.py

If a session already exists, it will not be erased or reset.

    % bliss -c demo
    Session 'demo' cannot be created: it already exists.

A session can be deleted with the `-d` option:

    % bliss -d docsession
     Removing 'docsession' session.
     removing .../sessions/docsession_setup.py
     removing .../sessions/docsession.yml
     removing .../sessions/scripts/docsession.py
