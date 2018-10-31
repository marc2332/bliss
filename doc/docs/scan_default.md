# Defaults BLISS scans

## BLISS scan functions

BLISS provides functions to perform scans a user would need for usual
step-by-step measurements.

The goal of all these functions is:

* to create an *acquisition chain*
* to forge a *title* and *type* (if not provided) based on scan parameters
* to check and to define *scan parameters* (motors, number of points, etc.)

These objects are then passed to `step_scan()` function to create a
`bliss.scanning.scan.Scan` object which can be run or returned to
caller. This class publishes data and triggers the file writer
(hdf5, cvs, SpecFile...) if any.


{% dot scan_dep.svg
   digraph scans_hierarchy {
   d2s [shape="box" label="d2scan"]
   a2s [shape="box" label="a2scan"]
   ls [shape="box" label="loopscan"]
   ct [shape="box" label="ct"]
   ts [shape="box" label="timescan"]
   lu [shape="box" label="lineup"]
   ds [shape="box" label="dscan"]
   as [shape="box" label="ascan"]
   ss [shape="box" label="step_scan"]
   ps [shape="box" label="pointscan"]
   dm [shape="box" label="dmesh"]
   am [shape="box" label="amesh"]

   d2s->a2s->ss
   ls->ts->ss
   lu->ds->as->ss
   ps->ss
   dm->am->ss
   ct->ts
   ss->"bliss.scanning.scan.Scan"
   }
%}


## Devices

Devices involved in standard scans must support
`INTERNAL_TRIGGER_MULTI` triggering mode.




## To go further...

To adapt the behaviour of scans and devices to the needs of the
measurement, there is some main way to operate:

* To make a unusual scan (like a 5-regions scans), a new scan has to
  be defined.
  See: [BLISS scan engine](scan_engine.md)
* To to change triggering or gating of intrument, is to adapt the
  *acquisition chain*.
  See: [Acquisition Chain](acq_chain.md)
* Customizing the presets. See: [Scans' presets](scan_presets.md)


## Parameters (common to all scans)

### Counters parameters
`counter_args` (counter-providing objects): each parameter provides
counters to be integrated in the scan.  if no counter parameters are
provided, use the active measurement group.


### Optional parameters
Common keyword arguments that can be used in all scans:

* `name (str)`: scan name in data nodes tree and directories [default: 'scan']
* `title (str)`: scan title [default: 'a2scan <motor1> ... <count_time>']
* `save (bool)`: save scan data to file [default: True]
* `save_images (bool)`: save image files [default: True]
* `sleep_time (float)`: sleep time between 2 points [default: None]
* `run (bool)`: if `True` (default), run the scan. `False` means to just create
    scan object and acquisition chain.
* `return_scan (bool)`: True by default ???

Q: diff entre return_scan=True et run=False ???

## Scan example

    ascan(<mot>, <start>, <stop>, <nb_points>, <acq_time>, <title>)
    ascan( sy,    1,       2,      3,           0.5, title="Jadarite_LiNaSiB3O7(OH)")

This command performs a scan of fifteen 500ms-counts of current
measurement group counters at `<sy>` motor positions 1, 1.5 and 2.


## ascan
    ascan(motor, start, stop, npoints, count_time, *counter_args, **kwargs)

Absolute scan.

Scans one motor, as specified by `<motor>`. The motor starts at the
position given by `<start>` and ends at the position given by
`<stop>`. The step size is `(<start>-<stop>)/(<npoints>-1)`. The number
of intervals will be `<npoints> - 1`. Count time is given by `<count_time>`
(seconds). 

At the end of the scan, the motor will stay at stopping position
(`<stop>` position in case of success).

## dscan
    dscan(motor, start, stop, npoints, count_time, *counter_args, **kwargs)

Relative scan.

Scans one motor, as specified by `<motor>`. If the motor is at
position *X* before the scan begins, the scan will run from
`X+start` to `X+end`.  The step size is
`(<start>-<stop>)/(<npoints>-1)`. The number of intervals will be
`<npoints>-1`. Count time is given by `<count_time>` (in seconds).

At the end of the scan (even in case of error) the motor will return to
its initial position.


## a2scan
    a2scan( motor1, start1, stop1,
            motor2, start2, stop2,
            npoints, count_time, *counter_args, **kwargs)

Absolute 2 motors scan.

Scans two motors, as specified by `<motor1>` and `<motor2>`. The motors start
at the positions given by `<start1>` and `<start2>` and end at the positions
given by `<stop1>` and `<stop2>`. The step size for each motor is given by
`(<start>-<stop>)/(<npoints>-1)`. The number of intervals will be
`<npoints>-1`. Count time is given by `<count_time>` (seconds).


## d2scan

Relative 2 motors scan.

Scans two motors, as specified by `<motor1>` and `<motor2>`. Each motor moves
the same number of points. If a motor is at position *X*
before the scan begins, the scan will run from `X+<start>` to `X+<end>`.
The step size of a motor is `(<start>-<stop>)/(<npoints>-1)`. The number
of intervals will be `<npoints>-1`. Count time is given by `<count_time>`
(in seconds).

At the end of the scan (even in case of error) the motors will return to
their initial positions.

## a3scan a4scan a5scan

Similary to `a2scan`, `aNscan` functions are provided fo N in {3,4,5}.

example:

    CYRIL [2]: a5scan(m1,1,2, m2,3,4, m3,5,6, m4,7,8, m5,8,9, 10, 0.1)
    Total 10 points, 0:00:04.100000 (motion: 0:00:03.100000, count: 0:00:01)
    
    Scan 2 Fri Oct 26 16:07:08 2018 /tmp/scans/cyril/ cyril user = guilloud
    a5scan m1 1 2 m2 3 4 m3 5 6 m4 7 8 m5 8 9 10 0.1
    
         #      dt[s]      m1      m2       m3       m4       m5      simct1
         0          0       1       3        5        7        8    0.038648
         1   0.432173    1.11    3.11     5.11     7.11     8.11    0.022345
         2   0.850866    1.22    3.22     5.22     7.22     8.22    0.119345
         3    1.25996    1.33    3.33     5.33     7.33     8.33     1.06995
         4    1.74734    1.44    3.44     5.44     7.44     8.44     3.45354
         5    2.16594    1.56    3.56     5.56     7.56     8.56     3.47793
         6    2.57817    1.67    3.67     5.67     7.67     8.67     1.01595
         7    2.98574    1.78    3.78     5.78     7.78     8.78    0.128783
         8     3.4303    1.89    3.89     5.89     7.89     8.89    0.073870
         9    3.84454       2       4        6        8        9    0.019919
    
    Took 0:00:05.226827 (estimation was for 0:00:04.100000)
      Out [2]: Scan(name=a5scan_2, run_number=2, path=/tmp/scans/cyril/)


## amesh
    amesh( motor1, start1, stop1, npoints1,
           motor2, start2, stop2, npoints2,
           count_time, *counter_args, **kwargs)

Mesh scan.

The amesh scan traces out a grid using motor `<motor1>` and motor `<motor2>`. The first
motor scans from position `<start1>` to `<end1>` using the specified number of
intervals. The second motor similarly scans from `<start2>` to `<end2>`. Each
point is counted for for time seconds (or monitor counts).

The scan of motor1 is done at each point scanned by motor2. That is,
the first motor scan is nested within the second motor scan. (motor1
is the "fast" axis, motor2 the "slow" axis)

*Special parameter*:

* `backnforth`: if True, do back and forth on the first motor.


## dmesh

Relative amesh.


## lineup

Relative scan.

    lineup(motor, start, stop, npoints, count_time, *counter_args, **kwargs)

lineup performs a `dscan` and then goes to the maximum value of first counter.


## timescan

Scan without movement.

    timescan(count_time, *counter_args, **kwargs)

Performs `<npoints>` counts for `<count_time>`. If `<npoints>` is 0, it
counts forever.

*Special parameters*:

* `output_mode (str)`: valid are 'tail' (append each line to output) or
'monitor' (refresh output in single line) [default: 'tail']
* `npoints (int)`: number of points [default: 0, meaning infinite number of points]

## loopscan

    loopscan(npoints, count_time, *counter_args, **kwargs)

Similar to `timescan` but `<npoints>` is mandatory.

## ct

    ct(count_time, *counter_args, **kwargs)

Counts for a specified time.


Note: This function blocks the current greenlet


## pointscan

Performs a scan over many positions given as a list.

    pointscan(motor, positions, count_time, *counter_args, **kwargs)

Scans one motor, as specified by `<motor>`. The motor starts at the position
given by the first value in `<positions>` and ends at the position given by last value `<positions>`.
Count time is given by `<count_time>` (seconds).

*Special parameter*:

* `positions`: List of positions to scan for `<motor>` motor.






