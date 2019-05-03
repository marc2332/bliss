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

Use `--no-tmux` to start a Bliss session without the Tmux terminal multiplexer.
In a Bliss session without Tmux, the scans output won't be printed in a separated window and will be shown in the main command line window.

    % bliss -s test_session --no-tmux