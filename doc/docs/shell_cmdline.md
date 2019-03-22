# BLISS command line usage

BLISS is a library, but a command line interface (*BLISS shell*) is
provided to easily and interactively execute BLISS *commands* and
*sequences* within an evolved REPL (Read Eval Print Loop).

## Usage

Use `-h` flag to get help about bliss command line interface:

        % bliss -h
        Usage: bliss [-l | --log-level=<log_level>] [-s <name> | --session=<name>]
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
            --show-sessions               Display available sessions and tree of sub-sessions
            --show-sessions-only          Display available sessions names only


### Version

Use `-v` or `--version` option to get the current version of a BLISS installation:

    % bliss --version
    BLISS version 0.2

### Logging level

`--log-level` or `-l` defines the logging level of the command line interface.

### Sessions

Use  `-s` or `--show-sessions` option to get the list of available sessions:

     % bliss --show-sessions
     Available BLISS sessions are:
       cyril

Other commands are also displaying the available sessions:

     % bliss --show-sessions-only
     % bliss -s

#### Automatic creation of a new session

Use `bliss --create` or `bliss -c` to create the skeleton of a new session:

    bliss -c eh1
    % bliss -c eh1
    creating 'eh1' session
    Creating: /bliss/users/guilloud/local/beamline_configuration/sessions/eh1_setup.py
    Creating: /bliss/users/guilloud/local/beamline_configuration/sessions/eh1.yml
    Creating: /bliss/users/guilloud/local/beamline_configuration/sessions/scripts/eh1.py

#### Removing an existing session

`bliss --delete` or `bliss -d` removes an existing session:

* session YAML file
* setup file
* default session script (see above)

