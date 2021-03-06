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

### mvd (dial move)
* `mvd([<motor>, <position>]+)`: moves motor(s) to given dial position(s).

```
DEMO [12]: mvd(simot1, 2, spec_m3, 4)
```

### umv (updated move)
* `umv([<motor>, <position>]+)`: same than `move([<motor>, <position>]+)` but
shows continuously updated positions of motors.

```
DEMO [13]: umv(simot1, 1, spec_m3, 4)

        simot1    spec_m3
user    0.390     3.258
dial    1.390     2.258
```

### umvd (updated dial move)
* `umvd([<motor>, <position>]+)`: same than `mvd([<motor>, <position>]+)` but
shows continuously updated positions of motors.

### mvr (relative move)
* `mvr([<motor>, <position>]+)`: move motor(s) relatively to current positions.
* `mvdr([<motor>, <position>]+)`: move motor(s) relatively to current dial positions.

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
        simot1
user    5.000
dial    4.000
```

### umvdr (updated dial relative move)
* `umdvr([<motor>, <position_increment>]+)`: Same than `mvdr()` but shows
continuously updated positions of motors.

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


### lsmot
* `lsmot()` : Print Motors configured in current session.

```python
DEMO [2]: lsmot()
Motors configured in current session:
-------------------------------------
att1z        bad              bsy        bsz        calc_mot1  calc_mot2
custom_axis  hooked_error_m0  hooked_m0  hooked_m1  jogger     m0
m1           omega            roby       robz       robz2      s1b
s1d          s1f              s1hg       s1ho       s1u        s1vg
s1vo
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

### tw (Tweak)
* `tw(<mot>)`: View motors in an user interface and move them
```python
tw(robz, roby, m0)
```

![Tweak screenshot](img/tweak_ui.png)
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


### lsobj
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


### lsconfig

* `lsconfig()`: print the list of BLISS objects in config, not only objects
  declared in current session.

Example:
```python
DEMO [2]: lsconfig()

MeasurementGroup:
----------------
demo_counters  MG_tomo  MG_sim  MG_gauss  MG_align

MultiplePositions:
-----------------
beamstop  att1

Motor:
-----
wl_mono     u42c     u42b    spec_m3  pzth_enc  pzth      psho         pshg
psf         psb      motor7  motor6   mono      mme       mm_enc       mm9
mm8         mm7      mm6     mm5      mm4       mm3       mm2          mm16
mm15        mm14     mm13    mm12     mm11      mm10      mm1          mech1
mc2         mc1_enc  mc1     mbv4mot  m5        m4        m3           m2
m1          kbvo     kbvg    kbho     kbhg      ice2      ice1         gal
fsh         e_mono   dummy2  dummy1   calc_mot  blade_up  blade_front  blade_down
blade_back  bend_u   bend_d

None:
----
ser0                 out1     kb1      hpz_rx               hpz_off_2
hpz_off_1            hppstc2  hppstc1  controller_setting3  controller_setting2
controller_setting1

SimulationCounter:
-----------------
sim_ct_calib_gauss3  sim_ct_calib_gauss2  sim_ct_calib_gauss  sim_ct_5  sim_ct_4
sim_ct_3             sim_ct_2             sim_ct_1            ct1

Session:
-------
test_session demo  cyril
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


### elog_print

`elog_print()` can be used like python's standard `print()` to send messages to the logbook.

### elog_add

The output from a previously execute command can be sent to the logbook
simply using `elog_add(num)`.
The parameter `num` con refer to the number of shell paragraph or be a
negative number relative to the current paragraph number.
If no parameter is specify the previous paragraph is sent (corresponds to -1).

Following an example sending to the logbook for three times the same output:

```python

TEST_SESSION [1]: transfocator_simulator
         Out [1]: Transfocator transfocator_simulator:
                  P0   L1  L2  L3  L4   L5  L6   L7  L8
                  OUT  IN  IN  IN  OUT  IN  OUT  IN  OUT

TEST_SESSION [2]: elog_add()  # adds previous paragraph (-1)
TEST_SESSION [3]: elog_add(1)  # can be used with reference to the paragraph number
TEST_SESSION [4]: elog_add(-3)  # can be also used with relative negative reference
```


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


### bench

* `bench()`: context manager to help benchmarking functions.

Example:

```python
DEMO [14]: with bench():
       ...:     time.sleep(1.987654)
Execution time: 1s 987ms 970??s
```
