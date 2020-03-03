# BLISS command line usage

BLISS is a library, but a command line interface (*BLISS shell*) is
provided to easily and interactively execute BLISS *commands* and
*sequences* within an evolved REPL (Read Eval Print Loop).

## Usage

Use `-h` flag to get help about bliss command line interface:

```
% bliss -h
Usage: bliss [-l | --log-level=<log_level>] [-s <name> | --session=<name>]
             [--no-tmux] [--debug]
       bliss [-v | --version]
       bliss [-c <name> | --create=<name>]
       bliss [-D <name> | --delete=<name>]
       bliss [-h | --help]
       bliss [-S | --show-sessions]
       bliss --show-sessions-only

Options:
  -l, --log-level=<log_level>   Log level [default: WARN]
                                (CRITICAL ERROR INFO DEBUG NOTSET)
  -s, --session=<session_name>  Start with the specified session
  -v, --version                 Show version and exit
  -c, --create=<session_name>   Create a new session with the given name
  -D, --delete=<session_name>   Delete the given session
  -h, --help                    Show help screen and exit
  --no-tmux                     Deactivate Tmux usage
  --debug                       Allow debugging with full exceptions and keeping
                                tmux alive after Bliss shell exits
  -S, --show-sessions           Display sessions and tree of sub-sessions
  --show-sessions-only          Display sessions names only
```

### Version

Use `-v` or `--version` option to get the current version of a BLISS installation:

```shell
% bliss --version
BLISS version 1.1.0
```

### Logging level

`--log-level` or `-l` defines the logging level of the command line interface.

### Sessions
Use `-s` to start an existing session:

```shell
% bliss -s test_session
                   __         __   __
                  |__) |   | /__` /__`
                  |__) |__ | .__/ .__/


Welcome to BLISS version 1.1.0 running on linohlsson2 (in bliss Conda environment)
Copyright (c) 2015-2020 Beamline Control Unit, ESRF
-
Connected to Beacon server on linohlsson2 (port /tmp/beacon_dnnmh7vl.sock)
test_session: Executing setup...

Welcome to your new 'test_session' BLISS session !! 

You can now customize your 'test_session' session by changing files:
   * /test_session_setup.py 
   * /test_session.yml 
   * /scripts/test_session.py 

Done.
```

Use `--show-sessions` option to get the list of available sessions:

```shell
% bliss --show-sessions
Available BLISS sessions are:
flint
  
lima_test_session
  
test_session
```

Other commands are also displaying the available sessions:

     % bliss --show-sessions-only

#### Creation of a new session

Use `--create` or `-c` to create the skeleton of a new session:

```shell
bliss -c eh1
% bliss -c eh1
Creating 'eh1' BLISS session
Creating sessions/eh1.yml
Creating sessions/eh1_setup.py
Creating sessions/scripts/eh1.py
```

#### Removing an existing session

To remove an existing session:

```shell
--delete or -D
```
this removes:

* session YAML file
* setup file
* default session script (see above)


## History

Previously typed commands can be recalled in the commnand line using up arrow
key `↑`.

History is kept in two distinct files depending of the usage of tmux or not:

* when using tmux it's in: `.start_bliss_repl.py_<session_name>_history`
* without tmux it's in: `.bliss_<session_name>_history`


Tmux provides an advanced history mode accessible with `F3` key:

* press `F3`
* BLISS shell is hidden
* terminal is split into two new panels: *history* and *temporary buffer*
* navigation in history is done with usual keys (`arrows` of `Ctrl-<key>`)
* hitting `Space` copy the current history line into temporary buffer
* hitting `Enter` switches back to BLISS shell with temporary buffer pasted


## Tmux

*Tmux* is a "terminal multiplexer". It creates a server where a BLISS session is
executed. If the client (graphical terminal for example) is closed or killed,
the server keeps running. Another client can then reconnect later.

This allows:

* to have multiple *panels* in a terminal (to split inputs and scan outputs)
* to share the view on a BLISS session (remote control)
* to keep a session alive even after exiting the graphical terminal where it
  runs.


### To share a session

If a session has been started with *Tmux*, another connection is possible. It must
be the **same user** and the joining is done in the same way than to start it:

```
bliss -s <session_name>
```

If a session is already running but without *Tmux* activated (ie with `--no-tmux`
flag), an error message is displayed:

```
-
Connected to Beacon server on linohlsson2 (port /tmp/beacon_dnnmh7vl.sock)
!!! === RuntimeError: demo is already running on host:linohlsson2,pid:8173 cmd: **bliss -s demo** === !!! ( for more details type cmd 'last_error' )
```

### To quit Tmux

To close a connection to a BLISS session running with *Tmux* without quiting the
session, use: `Ctrl-b d`

That is to say: press `Ctrl` and `b` at the same time, then `d` alone.

It should print: `[detached (from session demo)]`

### Multiple panels

The BLISS shell uses *Tmux* to handle multiple **panels**:

* The default one is the *"Bliss shell panel"* used to enter user
  commands and to display majority of answers to commands.
* The *Scan panel* is used to display output of scans.

This behavior has been introduced in order to avoid the user to be flooded by
scan outputs.

The `F5` key is used to switch between theses two panels.


### Deactivating Tmux

Use `--no-tmux` to start a Bliss session without the *Tmux* terminal
multiplexer. In a Bliss session without *Tmux*, the scans output won't
be printed in a separated window and will be shown in the main command
line window.

```shell
% bliss -s test_session --no-tmux
```

### Debugging within a Tmux session

By default, *Tmux* session is closed as soon as the Bliss shell exits.
In the case of an exception that forces Bliss shell to exit, the error information is lost.
In order to force *Tmux* to stay alive after Bliss shell exits, use the option `--debug`.
Also, it sets the `ERROR_REPORT.expert_mode` to `True` to allow a full print of the error and its traceback.

```shell
% bliss -s test_session --debug
```


### Mouse and Key bindings

* `MouseButtonLeft`:
    * drag to select area.
* `MouseButtonMiddle`:
    * Paste current selection
* `MouseButtonRight`:
    * exit copy-mode

* `Ctrl-b d`: Closes the connection without exiting the running BLISS session.

* `Up` or `Ctrl-p`: go one *line* up in history (line per line if multi-line command)
* `Down` or `Ctrl-n`: go one *line* down in history (line per line if multi-line command)
* `Ctrl-Left` or `Alt-b`: jump to begining of (previous) word
* `Ctrl-Right` or `Alt-f`: jump to end of (next) word
* `PageUp`: go one *command* up in history (group of lines if multi-line command)
* `PageDown`: go one *command* down in history (group of lines if multi-line command)
* `Ctrl-a` or `Home`: go to begining of the current line
* `Ctrl-e` or `End`: go to end of the current line
* `Shift-Up`: Scroll up terminal buffer by one line
* `Shift-Down`: Scroll down terminal buffer by one line
* `Shift-Home`: go to begining of terminal buffer
* `Shift-End`: go to end of terminal buffer

* `Ctrl-s`: search in current command

* Cutting and Pasting:
    * `Ctrl-w`: Cut the word before the cursor, adding it to the clipboard.
    * `Ctrl-k`: (emacs mode) Cut the part of the line after the
      cursor, adding it to the clipboard.
    * `Ctrl-u`: Cut the part of the line before the cursor, adding it to the clipboard.
    * `Ctrl-y`: (emacs mode) Paste the last thing you cut from the
      clipboard. The `y` here stands for “yank”.

* `Ctrl-Shift-_`: Undo your last key press. You can repeat this to undo multiple times.


* Function keys:
    * `F2`: *ptpython* Menu
    * `F3`: history mode:
        * BLISS shell is hidden
        * terminal is split into two new panels: *history* and *temporary buffer*
        * navigation in history is done with usual keys (`arrows` of `Ctrl-<key>`)
        * hitting `Space` copy the current history line into temporary buffer
        * hitting `Enter` switches back to BLISS shell with temporary buffer pasted
    * `F4`: switches `emacs` / `vi` mode (but why the hell to use vi ?)
    * `F5`: switches between *BLISS commands shell* and *scan display panel*
    * `F6`: switches to *paste mode* to paste code from external
      application forcing no automatic indentation.
    * `F7`: Disable typing helper (useful to copy/past code)
