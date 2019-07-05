# BLISS shell standard functions

use :

` from bliss.common.standard import *`

to get access to standard shell functions.

## motors

### move
`move([<motor>, <position>]+)` or `mv([<motor>, <position>]+)`: moves one or
many motors to given position(s).

```
DEMO [10]: mv(simot1, 2)
DEMO [11]: mv(simot1, 3, spec_m3, 5)
```

NB: `move()` can take `wait=False` argument to be non-bloquant.

### umv (updated move)
`umv([<motor>, <position>]+)`: same than `move([<motor>, <position>]+)` but
shows continuously updated positions of motors.

```
DEMO [13]: umv(simot1, 1, spec_m3, 4)

 simot1   spec_m3
   1.390     3.258
```

### mvr (relative move)
`mvr([<motor>, <position>]+)`: moves motor(s) relatively to current positions.

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
`umvr([<motor>, <position_increment>]+)`: Same than `mvr()` but shows
continuously updated positions of motors.

```python
CC4 [4]: umvr(m1, 1)
m1
5.000
```

### wa (where all)
`wa()`: Shows user and dial positions of configured motors.

```python
 DEMO [2]: wa()
 Current Positions (user, dial)
 
 pzth      simot1    spec_m3
 ------  --------  ---------
 !ERR     1.10000    1.46150
 !ERR     1.10000    1.46150
```

### wm (where motor)
`wm([<mot_name>]+)`: Shows user, dial and offset values of positions and limits
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
`sync([<motor>]*)`: Forces axes synchronization with the hardware. If no axis is
  given, it syncs all all axes present in the session

```python
DEMO [38]: sync(simot1)
```


## counters

### lscnt (show counters)
`lscnt()`:

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

### sta (motors status)
sta()`: Shows status of configured motors

```python
DEMO [13]: sta()
Axis     Status
-------  ----------------------
pzth     <status not available>
simot1   READY (Axis is READY)
spec_m3  READY (Axis is READY)
```

## introspection, doc, logging

### prdef (print definition)
`prdef(<function>)`: Displays information about given function :
 definition file, docstring and source code.

```python
CC4 [17]: prdef(umv)
'umv' is defined in:
/users/blissadm/conda/miniconda/envs/bliss/lib/python2.7/site-packages/bliss/common/standard.py:217

def umv(*args):
    """
    Moves given axes to given absolute positions providing updated display of
    the motor(s) position(s) while it(they) is(are) moving.

    Arguments are interleaved axis and respective absolute target position.
    """
    __umove(*args)
```

