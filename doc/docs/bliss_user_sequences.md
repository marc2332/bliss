
# User defined scripts and sequences

Python files from a local directory can be executed in a bliss session using the functions
`user_script_load(<file_name>)` or `user_script_run(<file_name>)`.

All commands in the file are executed. And each subsequent call re-execute the commands again.

A preferred directory can be set with the function `user_script_homedir()` and `user_script_list()` will display the python scripts available from this directory.

!!! hint "Script path can be absolute or relative"
    The functions `user_script_load()` and `user_script_run()` can take an absolute path for the script file
    or a path relative to the directory previously defined in the configuration or with the function `user_script_homedir()`.

!!! info "Error handling"
    In case of error, the functions `user_script_load()` and `user_script_run()` catch
    and display exceptions, and the script execution is stopped. Exceptions are printed not thrown.

## User script functions

### Run script

`user_script_run(script_name)` function executes all commands in the file. Nothing is exported to the current environment.

Argument:

* `script_name`: the python file to execute (relative or absolute path)

### Load script

`user_script_load(script_name)` function executes all commands in the file and export all symbols.

Argument:

* `script_name`: the python file to execute (relative or absolute path)

Optional argument:

* `export_global="user"` (default): export to a "user" namespace in current environment (and merge if pre-existing)
* `export_global=False`: return a namespace
* `export_global=True`: export to current environment

Return value:

* a namespace with all symbols defined or imported in this file

### Scripts home directory

`user_script_homedir()` function gives or set a preferred directory for user scripts for the current bliss session.

Once a preferred directory is set, it is stored as a setting in beacon server, and remembered
for the next time you open the session.

Arguments:

* `new_dir` (optional): absolute path of the scripts directory
* `reset` (optional, default is False): reset directory to default value (if any)

Return value:

* without argument the function returns the current user script directory.

!!! note "Default directory"
    There is no predefined user script directory by default.
    If none is set, you can still load scripts by giving an absolute path.

    You can specify a default directory by adding this line to a session .yml configuration file:

    `default-userscript-dir: <absolute_path_to_dir>`

### List available scripts

`user_script_list()` function displays all python scripts in the previously defined directory and its subdirectories.

## Examples

!!! example "Script file `/path/to/demo.py`"

    ```python

    import time
    # 'time' module is now usable in this file, but also in the session
    # 'demo' after loading of the script.

    print("[loading script] align_spectrometer()")

    # this function will be usable in the session once this script is loaded
    def align_spectrometer(energy=5.0):
        print(f"Aligning spectrometer for energy {energy} ...")
        time.sleep(1)
        print(f"Spectrometer is aligned :)")
    ```

### Example of script loading and usage:

```python
# Export to "user" namespace (default) in global env dict
DEMO [1]: user_script_load('/path/to/demo')
Loading [/path/to/demo.py]...
[loading script] align_spectrometer()
DEMO [2]:
DEMO [2]: user.align_spectrometer(energy=7.5)
Aligning spectrometer for energy 7.5 ...
Spectrometer is aligned :)
```

```python
# Export to a custom "demo" namespace in global env dict
DEMO [1]: user_script_load('/path/to/demo', export_global="demo")
Loading [/path/to/demo.py]...
[loading script] align_spectrometer()
DEMO [2]:
DEMO [2]: demo.align_spectrometer(energy=7.5)
Aligning spectrometer for energy 7.5 ...
Spectrometer is aligned :)
```

alternative usage:

```python
# Export to global env dict
DEMO [1]: user_script_load('/path/to/demo', export_global=True)
Loading [/path/to/demo.py]...
[loading script] align_spectrometer()
DEMO [2]:
DEMO [2]: align_spectrometer(energy=7.5)
Aligning spectrometer for energy 7.5 ...
Spectrometer is aligned :)
```

```python
# Return a namespace
DEMO [1]: demo = user_script_load('/path/to/demo', export_global=False)
Loading [/path/to/demo.py]...
[loading script] align_spectrometer()
DEMO [2]:
DEMO [2]: demo.align_spectrometer(energy=7.5)
Aligning spectrometer for energy 7.5 ...
Spectrometer is aligned :)
```
