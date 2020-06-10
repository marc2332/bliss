# BLISS shell standard functions

Standard shell functions are automatically accessible in shell of any BLISS
session.

## motors

### move
* `move([<motor>, <position>]+)` or `mv([<motor>, <position>]+)`: moves one or
many motors to given position(s).

```
DEMO [10]: mv(simot1, 2)
DEMO [11]: mv(simot1, 3, spec_m3, 5)
```

NB: `move()` can take `wait=False` argument to be non-bloquant.

### umv (updated move)
* `umv([<motor>, <position>]+)`: same than `move([<motor>, <position>]+)` but
shows continuously updated positions of motors.

```
DEMO [13]: umv(simot1, 1, spec_m3, 4)

 simot1   spec_m3
   1.390     3.258
```

### mvr (relative move)
* `mvr([<motor>, <position>]+)`: move motor(s) relatively to current positions.

```python
DEMO [5]: wa()
Current Positions (user, dial)

   simot1    spec_m3
 --------  ---------
  3.00000    7.00000
  3.00000    7.00000

DEMO [6]: mvr(simot1, 1, spec_m3, 2)

DEMO [7]: wa()
Current Positions (user, dial)

  simot1    spec_m3
--------  ---------
 4.00000    9.00000
 4.00000    9.00000
```

### umvr (updated relative move)
* `umvr([<motor>, <position_increment>]+)`: Same than `mvr()` but shows
continuously updated positions of motors.

```python
CC4 [4]: umvr(m1, 1)
m1
5.000
```

### wa (where all)
* `wa()`: Shows user and dial positions of configured motors.

```python
 DEMO [2]: wa()
 Current Positions (user, dial)
 
 pzth      simot1    spec_m3
 ------  --------  ---------
 !ERR     1.10000    1.46150
 !ERR     1.10000    1.46150
```

### wm (where motor)
* `wm([<mot_name>]+)`: Show user, dial and offset values of positions and limits
for given motor(s).

```python
DEMO [2]: wm(m1, m2)

             m1[mm]          m2
-------  ----------  ----------
User
High      128.00000  -123.00000
Current     7.00000   -12.00000
Low      -451.00000   456.00000
Offset      5.00000     0.00000
Dial
High      123.00000   123.00000
Current     2.00000    12.00000
Low      -456.00000  -456.00000
```

### sync
* `sync([<motor>]*)`: Force axes synchronization with the hardware. If no axis is
  given, it syncs all all axes present in the session

```python
DEMO [38]: sync(simot1)
```

### sta (all motors status)
* `sta()`: Show status of all configured motors.

```python
DEMO [13]: sta()
Axis     Status
-------  ----------------------
pzth     <status not available>
simot1   READY (Axis is READY)
spec_m3  READY (Axis is READY)
```

### stm (motors status)
* `stm(<mot>)`: Show status of motors given as parameters.

```python
DEMO [3]: stm(mm1, mm2)
Axis    Status
------  ---------------------
mm1     READY (Axis is READY)
mm2     READY (Axis is READY)
```

### rockit (rock a motor around current position)

* `rockit(mot, total_move):` Rock the motor **mot** around it's current
position +/- total_move/2.

i.e: Rock the motor mm1 during a ascan. At the end of the *context*,
the rocking will stop and the motor **mm1** will be moved back the
previous position.

```python
with rockit(mm1, 10):
     ascan(mm2,0,2,10,0.1,diode)

```


## counters

### lscnt (list counters)
* `lscnt()`:

```python
DEMO [1]: lscnt()

Name                     Shape    Controller
-----------------------  -------  ------------
simct1                   0D       None
simct2                   0D       None
simct3                   0D       None
simct4                   0D       None
simul_mca.AuLa           0D       simul_mca
simul_mca.AuLa_det0      0D       simul_mca
simul_mca.AuLa_det1      0D       simul_mca
simul_mca.AuLa_det2      0D       simul_mca
simul_mca.AuLa_det3      0D       simul_mca
simul_mca.deadtime_det0  0D       simul_mca
simul_mca.deadtime_det1  0D       simul_mca
```


## Bliss Objects

* `lsobj()`: print the list of BLISS objects defined in a session. Can be used
  with usual jocker characters:

    - `*`: matches everything
    - `?`: matches any single character
    - `[seq]`: matches any character in seq
    - `[!seq]`: matches any character not in seq

Examples:
```python
TEST_SESSION [2]: lsobj("dio*")      # all objects starting by 'dio'
diode  diode2  diode3  diode4  diode5  diode6  diode7  diode8  diode9

TEST_SESSION [3]: lsobj("[abc]*")    # all objects starting by 'a', 'b' or 'c'
beamstop  att1  bad  calc_mot1  calc_mot2  custom_axis

TEST_SESSION [6]: lsobj("???")       # all objects with 3-lettres names
MG1  MG2  bad  s1b  s1d  s1f  s1u
```

## Data Policy
* `newproposal()` `newsample()` `newdataset()`: Change the **proposal** **sample**
and **dataset** names used to determine the saving path.

For more info about these three functions, see [data policy
section](bliss_data_policy.md#directory-structure)


## Display

* `plotselect()`: select counter(s) to plot in [Flint](bliss_flint.md#command-line-selection)

* `clear()`: clear the screen.

* `silx_view()`: launch Silx View on last scan's data file.

* `pymca()`: launch PyMca on last scan's data file.

## Dialogs

Some bliss objects can be used with dialogs.

To check if an object has dialogs implemented you can use the `menu` function.

Using `menu()` without further arguments will display all objects that has
dialogs implemented.

Using using `menu(object)` will launch the dialog with his effects. If more than
one dialog exists for the same object you can either pass the dialog name as a string
like `menu(lima_simulator, "saving")` or just use `menu(lima_simulator)` and first
you will select between available dialogs and than use the selected one.

Using

```python
TEST_SESSION [2]: menu()  
         Out [2]: Dialog available for the following objects:

                  ACTIVE_MG
                  MG1
                  MG2
                  ascan
                  lima_simulator
                  test_mg
                  transfocator_simulator
                  wago_simulator
                  ...

TEST_SESSION [3]: show(trasfocator_simulator)
                  .. HERE THE DIALOG DISPLAYS ..
         Out [3]: Transfocator transfocator_simulator:  # effects of dialog
                  P0  L1  L2   L3  L4   L5   L6  L7  L8
                  IN  IN  OUT  IN  OUT  OUT  IN  IN  IN

TEST_SESSION [4]: show(lima_simulator, "saving")
                  .. HERE THE DIALOG DISPLAYS ..
         Out [4]: # display of return status if present

TEST_SESSION [5]: show(lima_simulator)
                  .. HERE SUBMENU DIALOG DISPLAYS ..
                  .. THAN SELECTED DIALOG DISPLAYS ..
         Out [5]: # display of return status if present
```


## Wago Interlocks

* `interlock_show([wago]*)`: display interlocks info for given Wagos (for all
wagos if no parameter is given).

* `interlock_state()`: return a tuple containing the actual state of the
  interlocks.


## introspection, doc, logging

### Logging and Debug

* `lslog()`: display the list of [loggers](shell_logging.md#lslog).

* `lsdebug()`: display the list of [loggers currently in debug
  mode](shell_logging.md#lslog).

* `debugon()`/`debugoff()`: activate/deactivate
  [debug](shell_logging.md#debugon-debugoff) on a BLISS object.


### logbook print

* `lprint()`: replacement for python standard `print()` this function that sends
what is given to both stdout and to the logbook.

Everything that should be logged to the logbook for any reason should use this
instead of the normal print.

You can use `lprint()` even when using Bliss in library mode: no output will
be send to stdout, but messages will be forwarded to logbook.

### prdef (print definition)
* `prdef(<function>)`: Display information about given function :
 definition file, docstring and source code.

```python
CC4 [17]: prdef(umv)
'umv' is defined in:
/users/blissadm/..../site-packages/bliss/common/standard.py:217

def umv(*args):
    """
    Moves given axes to given absolute positions providing updated display of
    the motor(s) position(s) while it(they) is(are) moving.

    Arguments are interleaved axis and respective absolute target position.
    """
    __umove(*args)
```

### ladd

The output from a previously execute command can be sent to the logbook
simply using `ladd(num)`.
The parameter `num` con refer to the number of shell paragraph or be a
negative number relative to the current paragraph number.
If no parameter is specify the previous paragraph is sent (coresponds to -1).

Following an example sending to the logbook for three times the same output:

```python

TEST_SESSION [1]: transfocator_simulator
         Out [1]: Transfocator transfocator_simulator:
                  P0   L1  L2  L3  L4   L5  L6   L7  L8
                  OUT  IN  IN  IN  OUT  IN  OUT  IN  OUT

TEST_SESSION [2]: ladd()  # adds previous paragraph (-1)
TEST_SESSION [3]: ladd(1)  # can be used with reference to the paragraph number
TEST_SESSION [4]: ladd(-3)  # can be also used with relative negative reference
```

### bench

* `bench()`: context manager to help benchmarking functions.

Example:

```python
DEMO [14]: with bench():
       ...:     time.sleep(1.987654)
Execution time: 1s 987ms 970μs
```
