# BLISS command line usage

BLISS is a library, but a command line interface (*BLISS shell*) is
provided to easily and interactively execute BLISS *commands* and
*sequences* within an evolved REPL (Read Eval Print Loop).

## Usage

Use `-h` flag to get help about bliss command line interface:

```
% bliss -h
Usage: bliss [-l | --log-level=<log_level>] [-s <name> | --session=<name>]
             [--no-tmux]
       bliss [-v | --version]
       bliss [-c <name> | --create=<name>]
       bliss [-d <name> | --delete=<name>]
       bliss [-h | --help]
       bliss --show-sessions
       bliss --show-sessions-only

Options:
    -l, --log-level=<log_level>   Log level [default: WARN]
                                  {CRITICAL; ERROR; INFO; DEBUG; NOTSET}
    -s, --session=<session_name>  Start with the specified session
    -v, --version                 Show version and exit
    -c, --create=<session_name>   Create a new session with the given name
    -d, --delete=<session_name>   Delete the given session
    -h, --help                    Show help screen and exit
    --no-tmux                     Deactivate Tmux usage
    --show-sessions               Display sessions and tree of sub-sessions
    --show-sessions-only          Display sessions names only
```

### Version

Use `-v` or `--version` option to get the current version of a BLISS installation:

```
% bliss --version
BLISS version 0.2
```

### Logging level

`--log-level` or `-l` defines the logging level of the command line interface.

### Sessions
Use `-s` to start an existing session:

```
% bliss -s test_session
                   __         __   __
                  |__) |   | /__` /__`
                  |__) |__ | .__/ .__/


Welcome to BLISS version erbs5c2 running on PCGUILLOU
                                         in bliss_env Conda environment
Copyright (c) ESRF, 2015-2019
```

Use `--show-sessions` option to get the list of available sessions:

```
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

```
bliss -c eh1
% bliss -c eh1
creating 'eh1' session
Creating: /.../local/beamline_configuration/sessions/eh1_setup.py
Creating: /.../local/beamline_configuration/sessions/eh1.yml
Creating: /.../local/beamline_configuration/sessions/scripts/eh1.py
```

#### Removing an existing session

`--delete` or `-d` removes an existing session:

* session YAML file
* setup file
* default session script (see above)


## Multiple panels (Tmux)

The BLISS shell uses *Tmux* to handle multiple **panels**:

* The default one is the *"Bliss shell panel"* used to enter user
  commands and to display majority of answers to commands.
* The *Scan panel* is used to display output of scans. It is
  automaticaly displayed when a scan starts.

This behaviour has been introduced in order to avoid the used to be
flooded by scan outputs.

The `F5` key is used to switch between thoses two panels.


#### Deactivating Tmux (terminal multiplexer) usage

Use `--no-tmux` to start a Bliss session without the Tmux terminal
multiplexer. In a Bliss session without Tmux, the scans output won't
be printed in a separated window and will be shown in the main command
line window.

```
% bliss -s test_session --no-tmux
```


### Mouse and Key bindings in Tmux

* `MouseButtonLeft`:
    * drag to select area.
* `MouseButtonMiddle`:
    * Paste current selection
* `MouseButtonRight`:
    * exit copy-mode

* `Up` or `Ctrl-p`: go one *line* up in history (line per line if multi-line command)
* `Down` or `Ctrl-n`: go one *line* down in history (line per line if multi-line command)
* `Ctrl-Left` or `Alt-b`: jump to begining of (previous) word
* `Ctrl-Right` or `Alt-f`: jump to end of (next) word
* `PageUp`: go one *command* up in history (group of lines if multi-line command)
* `PageDown`: go one *command* down in history (group of lines if multi-line command)
* `Ctrl-a` or `Home`: go to begining of the current line
* `Ctrl-e` or `End`: go to end of the current line
* `Shift-PageUp`: Scroll up terminal buffer by half a page
* `Shift-PageDown`: Scroll down terminal buffer by half a page
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
    * `F1`: ?
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

