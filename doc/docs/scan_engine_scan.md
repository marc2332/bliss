Is the top level object of the scan engine and it's the one who
performe the scan according to the [acquisition
chain](scan_engine_acquisition_chain.md) passed as argument when
calling the `run` method.  It save and publish Acquisition data
following the configuartion of [scan
saving](gs_presentation.md#scan-saving).

## Scan data

During or after the scan, you can retrieved the scan data by calling
`get_data` method.  This will return datas as a dictionnary with the
key as the counter name and a numpy array with the assaociated data.

```python
TEST_SESSION [1]: s = loopscan(2,0.1,diode)
Total 2 points, 0:00:00.200000 (motion: 0:00:00, count: 0:00:00.200000)

Scan 3 Wed Mar 06 11:47 /scans/test_session/data.h5 test_session user = seb
loopscan 2 0.1

           #         dt[s]         diode
           0             0       2.77778
           1      0.107661            26

Took 0:00:03.523786 (estimation was for 0:00:00.200000)

TEST_SESSION [2]: s.get_data().keys()
         Out [2]: dict_keys(['elapsed_time', 'diode'])


TEST_SESSION [3]: s.get_data()['diode']
         Out [3]: array([ 2.77777778, 26. ])
```

## Alignment functions

There is a group of function that returns motor position in fonction
of value of counter passed as argument.  Available function are:

   * `fwhm` return the *full width half maximum*
   * `cen` return the *center of the fwhm* and *fwhm*
   * `com` return the *center of mass*xs
   * `peak` return the motor position at the counter *maximum*

An other function group prefixed by `goto_` move directly the motor to
the calculated position. i.e: `goto_cen` move the motor to the *center
of the fwhm*. This group of function draw a marker in flint at the
final motor position.

Function `where` display the current scan motor position.

### Example

```python
TEST_SESSION [1]: s = ascan(robz,0,1,10,0.1,counter)
Total 10 points, 0:00:01.480618 (motion: 0:00:00.480618, count: 0:00:01)

Scan 7 Wed Mar 06 12:45 /scans/test_session/data.h5 test_session user = seb
ascan robz 0 1 10 0.1

           #         dt[s]          robz   autoCounter
           0             0             0     0.0526115
           1      0.205485        0.1111     0.0731554
           2       0.40605        0.2222      0.107844
           3      0.606267        0.3333       1.07414
           4      0.800804        0.4444       3.49636
           5       1.00134        0.5556       3.43307
           6       1.20344        0.6667       1.04448
           7       1.40291        0.7778      0.147452
           8       1.60499        0.8889      0.035737
           9       1.80242             1     0.0652613

Took 0:00:02.167129 (estimation was for 0:00:01.480618)
TEST_SESSION [2]: robz.position #position of robz at the end of scan
         Out [2]: 1.0

TEST_SESSION [3]: s.cen(counter)
         Out [3]: (0.49405354172988597, 0.42511754017698633)

TEST_SESSION [4]: s.goto_cen(counter) #will move to 0.49405354172988597

TEST_SESSION [5]: robz.position #position after the `goto_cen`
         Out [5]: 0.4941
```

## Profiling

Some execution timing are calculated at each scan. They can be
displayed on demand:

```python
DEMO [16]: SCANS[-1].statistics
  Out [16]: func_name               min        mean       max            std
            ----------------------  ---------  ---------  ---------  -------
            sim_acq_dev.prepare     116.825us  116.825us  116.825us  0.00000
            sim_acq_dev.start       595.093us  595.093us  595.093us  0.00000
            sim_acq_dev.stop        178.814us  178.814us  178.814us  0.00000
            sim_acq_dev.trigger     58.174us   344.356us  607.014us  0.00022
            sim_acq_dev.wait_ready  151.873us  247.002us  313.044us  0.00007
            timer.prepare           53.883us   129.938us  179.052us  0.00005
            timer.start             514.895ms  839.220ms  1.002s     0.22933
            timer.stop              211.954us  211.954us  211.954us  0.00000
            timer.trigger_slaves    92.983us   209.570us  301.838us  0.00009
            timer.wait_ready        194.073us  270.685us  356.913us  0.00007
            timer.wait_slaves       200.987us  330.567us  536.203us  0.00014
```

more details in [acquisition statistics](scan_engine_acquisition_chain.md#statistics)

## Debugging

To debug scans, there is a tracing mechanism.
Use:`

* `debugon("bliss.scans")` to activate it
* `debugoff("bliss.scans")` to de-activate it


### Scan example


```python
DEMO [14]: s = timescan(1, sim_acq_dev.counters.sc1, run=False)

DEMO [15]: debugon("bliss.scans")

DEMO [16]: s.run()
Total 0 points

Scan 7 Fri Nov 30 13:31:15 2018 /tmp/scans/cyril/ cyril user = guilloud
timescan 1

           #         dt[s]           sc1
DEBUG 2018-11-30 13:31:15,050 Scan: Start timer.wait_ready
DEBUG 2018-11-30 13:31:15,050 Scan: End timer.wait_ready Took 0.000194s
DEBUG 2018-11-30 13:31:15,051 Scan: Start sim_acq_dev.wait_ready
DEBUG 2018-11-30 13:31:15,051 Scan: End sim_acq_dev.wait_ready Took 0.000152s
DEBUG 2018-11-30 13:31:15,061 Scan: Start sim_acq_dev.prepare
DEBUG 2018-11-30 13:31:15,061 Scan: End sim_acq_dev.prepare Took 0.000117s
DEBUG 2018-11-30 13:31:15,061 Scan: Start timer.prepare
DEBUG 2018-11-30 13:31:15,061 Scan: End timer.prepare Took 0.000054s
DEBUG 2018-11-30 13:31:15,062 Scan: Start sim_acq_dev.start
DEBUG 2018-11-30 13:31:15,062 Scan: End sim_acq_dev.start Took 0.000595s
DEBUG 2018-11-30 13:31:15,063 Scan: Start timer.start
DEBUG 2018-11-30 13:31:15,063 Scan: Start timer.trigger_slaves
DEBUG 2018-11-30 13:31:15,063 Scan: End timer.trigger_slaves Took 0.000093s
DEBUG 2018-11-30 13:31:15,063 Scan: Start sim_acq_dev.trigger
DEBUG 2018-11-30 13:31:15,063 Scan: End sim_acq_dev.trigger Took 0.000058s
DEBUG 2018-11-30 13:31:15,064 Scan: Start timer.wait_slaves
DEBUG 2018-11-30 13:31:15,065 Scan: End timer.wait_slaves Took 0.000201s
           0             0            44
DEBUG 2018-11-30 13:31:16,064 Scan: End timer.start Took 1.001576s
DEBUG 2018-11-30 13:31:16,065 Scan: Start timer.wait_ready
DEBUG 2018-11-30 13:31:16,065 Scan: End timer.wait_ready Took 0.000261s
DEBUG 2018-11-30 13:31:16,065 Scan: Start sim_acq_dev.wait_ready
DEBUG 2018-11-30 13:31:16,066 Scan: End sim_acq_dev.wait_ready Took 0.000276s
DEBUG 2018-11-30 13:31:16,066 Scan: Start timer.prepare
DEBUG 2018-11-30 13:31:16,066 Scan: End timer.prepare Took 0.000157s
DEBUG 2018-11-30 13:31:16,067 Scan: Start timer.start
DEBUG 2018-11-30 13:31:16,068 Scan: Start timer.trigger_slaves
DEBUG 2018-11-30 13:31:16,068 Scan: End timer.trigger_slaves Took 0.000302s
DEBUG 2018-11-30 13:31:16,069 Scan: Start sim_acq_dev.trigger
DEBUG 2018-11-30 13:31:16,069 Scan: End sim_acq_dev.trigger Took 0.000607s
DEBUG 2018-11-30 13:31:16,073 Scan: Start timer.wait_slaves
DEBUG 2018-11-30 13:31:16,073 Scan: End timer.wait_slaves Took 0.000536s
           1       1.00468            44
DEBUG 2018-11-30 13:31:17,068 Scan: End timer.start Took 1.001188s
DEBUG 2018-11-30 13:31:17,069 Scan: Start timer.wait_ready
DEBUG 2018-11-30 13:31:17,069 Scan: End timer.wait_ready Took 0.000357s
DEBUG 2018-11-30 13:31:17,070 Scan: Start sim_acq_dev.wait_ready
DEBUG 2018-11-30 13:31:17,070 Scan: End sim_acq_dev.wait_ready Took 0.000313s
DEBUG 2018-11-30 13:31:17,071 Scan: Start timer.prepare
DEBUG 2018-11-30 13:31:17,071 Scan: End timer.prepare Took 0.000179s
DEBUG 2018-11-30 13:31:17,072 Scan: Start timer.start
DEBUG 2018-11-30 13:31:17,072 Scan: Start timer.trigger_slaves
DEBUG 2018-11-30 13:31:17,072 Scan: End timer.trigger_slaves Took 0.000234s
DEBUG 2018-11-30 13:31:17,073 Scan: Start sim_acq_dev.trigger
DEBUG 2018-11-30 13:31:17,073 Scan: End sim_acq_dev.trigger Took 0.000368s
DEBUG 2018-11-30 13:31:17,075 Scan: Start timer.wait_slaves
           2       2.00908            44
DEBUG 2018-11-30 13:31:17,075 Scan: End timer.wait_slaves Took 0.000373s
^C
ERROR 2018-11-30 13:31:17,586 Scan: Exception caught in timer.start
DEBUG 2018-11-30 13:31:17,586 Scan: End timer.start Took 0.514895s
DEBUG 2018-11-30 13:31:17,587 Scan: Start timer.stop
DEBUG 2018-11-30 13:31:17,587 Scan: End timer.stop Took 0.000212s
DEBUG 2018-11-30 13:31:17,588 Scan: Start sim_acq_dev.stop
--SAD ACQDEV: stop()
DEBUG 2018-11-30 13:31:17,588 Scan: End sim_acq_dev.stop Took 0.000179s
DEBUG 2018-11-30 13:31:17,588 Scan: Start timer.wait_slaves
DEBUG 2018-11-30 13:31:17,589 Scan: End timer.wait_slaves Took 0.000212s

Took 0:00:02.564716
KeyboardInterrupt
```

### ct example

```python
DEMO [4]: s = ct(1, sim_acq_dev.counters.sc1,run=False)

DEMO [6]: debugon("bliss.scans");s.run()

DEBUG 2018-11-30 13:27:20,823 Scan: Start timer.wait_ready
DEBUG 2018-11-30 13:27:20,823 Scan: End timer.wait_ready Took 0.000339s
DEBUG 2018-11-30 13:27:20,824 Scan: Start sim_acq_dev.wait_ready
DEBUG 2018-11-30 13:27:20,824 Scan: End sim_acq_dev.wait_ready Took 0.000282s
DEBUG 2018-11-30 13:27:20,831 Scan: Start sim_acq_dev.prepare
DEBUG 2018-11-30 13:27:20,831 Scan: End sim_acq_dev.prepare Took 0.000147s
DEBUG 2018-11-30 13:27:20,831 Scan: Start timer.prepare
DEBUG 2018-11-30 13:27:20,831 Scan: End timer.prepare Took 0.000098s
DEBUG 2018-11-30 13:27:20,832 Scan: Start sim_acq_dev.start
DEBUG 2018-11-30 13:27:20,832 Scan: End sim_acq_dev.start Took 0.000187s
DEBUG 2018-11-30 13:27:20,832 Scan: Start timer.start
DEBUG 2018-11-30 13:27:20,833 Scan: Start timer.trigger_slaves
DEBUG 2018-11-30 13:27:20,833 Scan: End timer.trigger_slaves Took 0.000092s
DEBUG 2018-11-30 13:27:20,833 Scan: Start sim_acq_dev.trigger
DEBUG 2018-11-30 13:27:20,833 Scan: End sim_acq_dev.trigger Took 0.000093s
DEBUG 2018-11-30 13:27:20,834 Scan: Start timer.wait_slaves
DEBUG 2018-11-30 13:27:20,834 Scan: End timer.wait_slaves Took 0.000239s
Fri Nov 30 13:27:20 2018

  dt[s] =          0.0 (         0.0/s)
    sc1 =         44.0 (        44.0/s)
DEBUG 2018-11-30 13:27:21,834 Scan: End timer.start Took 1.001465s
DEBUG 2018-11-30 13:27:21,835 Scan: Start timer.wait_ready
DEBUG 2018-11-30 13:27:21,835 Scan: End timer.wait_ready Took 0.000342s
DEBUG 2018-11-30 13:27:21,836 Scan: Start sim_acq_dev.wait_ready
DEBUG 2018-11-30 13:27:21,836 Scan: End sim_acq_dev.wait_ready Took 0.000356s
DEBUG 2018-11-30 13:27:21,836 Scan: Start timer.wait_slaves
DEBUG 2018-11-30 13:27:21,837 Scan: End timer.wait_slaves Took 0.000266s
DEBUG 2018-11-30 13:27:21,839 Scan: Start timer.stop
DEBUG 2018-11-30 13:27:21,839 Scan: End timer.stop Took 0.000218s
DEBUG 2018-11-30 13:27:21,839 Scan: Start sim_acq_dev.stop
DEBUG 2018-11-30 13:27:21,839 Scan: End sim_acq_dev.stop Took 0.000049s
DEBUG 2018-11-30 13:27:21,840 Scan: Start timer.wait_slaves
DEBUG 2018-11-30 13:27:21,840 Scan: End timer.wait_slaves Took 0.000060s
  Out [6]: Scan(name=ct_6, run_number=6)
```
