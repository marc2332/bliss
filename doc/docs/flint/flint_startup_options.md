## Flint startup options

Flint startup can be tuned using the following command line arguments and
settings.

A command line argument use to override over equivalent settings.

### Command line arguments

```
  -h, --help            Show this help message and exit
  -V, --version         Show program's version number and exit
  --debug               Set logging system in debug mode
  --enable-opengl, --gl
                        Enable OpenGL rendering. It provides a faster
                        rendering for plots but could have issue with remote
                        desktop (default: matplotlib is used)
  --disable-opengl      Disable OpenGL rendering. Use matplotlib by default
                        for this execution)
  --disable-share-opengl-contexts
                        Disable AA_ShareOpenGLContexts used by Qt in order to
                        prevent segmentation fault with some environment.
  --enable-simulator    Enable scan simulation panel
  --enable-gevent-poll  Enable system patching of the 'poll' function in order
                        to create a cooperative event loop between Qt and
                        gevent. It processes efficiently events from fast
                        acquisition scans but could be unstable (experimental)
  --matplotlib-dpi MATPLOTLIB_DPI
                        Set the DPI used for the matplotlib backend. This
                        value will be stored in the user preferences (default:
                        100)
  --clear-settings      Start with cleared local user settings.
  --bliss-session BLISS_SESSION
                        Start Flint an connect it to a BLISS session name.
  --log-file LOG_FILE   Store logs in a file.
```

### Command line arguments inside BLISS

BLISS can use a specific list of command line arguments when starting Flint.

The global object `SCAN_DISPLAY` provides a property `extra_args` which can be
set with the list of needed arguments. This setting is stored per BLISS session.

Here is an example:
```
SCAN_DISPLAY.extra_args = ["--disable-opengl", "--disable-share-opengl-contexts"]
```

The following line remove the setting:
```
SCAN_DISPLAY.extra_args = []
```

As the list is validated when it is set, the list of the command line arguments
can be displayed with this trick:
```
SCAN_DISPLAY.extra_args = ["--help"]
```

### INI file configuration

A master `.ini` file is read by Flint.

Depending on your operating system, this file can be fount at `~/.config/ESRF/flint.ini`.

It mostly stores the location of the windows per session/screen. But it also
contains few flags to fix specific problems relative to the machine.

- `share-opengl-contexts`
    Flint uses `AA_ShareOpenGLContexts` in order to make it work well with OpenGL
    and docks. This can cause segmentation fault for some machines.
    To prevent that, the following flag can be setup.

```
[qapplication]
share-opengl-contexts=false
```
