# BLISS command line usage

BLISS is a library, but a command line interface (*BLISS shell*) is
provided to easily and interactively execute BLISS *commands* and
*sequences* within an evolved REPL (Read Eval Print Loop).

## Usage

Use `-h` flag to get help about bliss command line interface:

        % bliss -h
        Usage: bliss [-l | --log-level=<log_level>] [-s <name> | --session=<name>] [--no-tmux]
               bliss [-v | --version]
               bliss [-c <name> | --create=<name>]
               bliss [-d <name> | --delete=<name>]
               bliss [-h | --help]
               bliss --show-sessions
               bliss --show-sessions-only
        
        Options:
            -l, --log-level=<log_level>   Log level [default: WARN] (CRITICAL ERROR INFO DEBUG NOTSET)
            -s, --session=<session_name>  Start with the specified session
            -v, --version                 Show version and exit
            -c, --create=<session_name>   Create a new session with the given name
            -d, --delete=<session_name>   Delete the given session
            -h, --help                    Show help screen and exit
            --no-tmux                     Deactivate Tmux usage
            --show-sessions               Display available sessions and tree of sub-sessions
            --show-sessions-only          Display available sessions names only


### Version

Use `-v` or `--version` option to get the current version of a BLISS installation:

    % bliss --version
    BLISS version 0.2

### Logging level

`--log-level` or `-l` defines the logging level of the command line interface.

### Sessions
Use `-s` to start an existing session:

    % bliss -s test_session
                       __         __   __
                      |__) |   | /__` /__`
                      |__) |__ | .__/ .__/


    Welcome to BLISS version 1e7eb5c2 running on PCGUILLOU (in bliss_env Conda environment)
    Copyright (c) ESRF, 2015-2018

Use `--show-sessions` option to get the list of available sessions:

     % bliss --show-sessions
     Available BLISS sessions are:
       flint
       lima_test_session
       test_session

Other commands are also displaying the available sessions:

     % bliss --show-sessions-only

#### Automatic creation of a new session

Use `--create` or `-c` to create the skeleton of a new session:

    bliss -c eh1
    % bliss -c eh1
    creating 'eh1' session
    Creating: /bliss/users/guilloud/local/beamline_configuration/sessions/eh1_setup.py
    Creating: /bliss/users/guilloud/local/beamline_configuration/sessions/eh1.yml
    Creating: /bliss/users/guilloud/local/beamline_configuration/sessions/scripts/eh1.py

#### Removing an existing session

`--delete` or `-d` removes an existing session:

* session YAML file
* setup file
* default session script (see above)

#### Deactivating Tmux (terminal multiplexer) usage

Use `--no-tmux` to start a Bliss session without the Tmux terminal
multiplexer.  In a Bliss session without Tmux, the scans output won't
be printed in a separated window and will be shown in the main command
line window.

    % bliss -s test_session --no-tmux


### Mouse and Key bindings in Tmux

* `MouseButtonLeft`:
    * drag to select area.
* `MouseButtonMiddle`:
    * Paste current selection
* `MouseButtonRight`:
    * exit copy-mode

* `up`: go one *line* up in history (line per line if multi-line command)
* `down`: go one *line* down in history (line per line if multi-line command)
* `Ctrl-Left`: jump to begining of (previous) word
* `Ctrl-Right`: jump to end of (next) word
* `PageUp`: go one *command* up in history (group of lines if multi-line command)
* `PageDown`: go one *command* down in history (group of lines if multi-line command)
* `Home`: go to begining of the current line
* `End`: go to end of the current line
* `Shift-PageUp`: Scroll up terminal buffer by half a page
* `Shift-PageDown`: Scroll down terminal buffer by half a page
* `Shift-Up`: Scroll up terminal buffer by one line
* `Shift-Down`: Scroll down terminal buffer by one line
* `Shift-Home`: go to begining of terminal buffer
* `Shift-End`: go to end of terminal buffer

* `Ctrl-s`: search in current command

TODO:

* `Ctrl-a`: go to begining of the current line
* `Ctrl-e`: go to end of the current line

