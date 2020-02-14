
# Flint Scan Plotting

On BLISS, online data display relies on **flint**, a graphical application built on top of [silx][1] (ScIentific Library for eXperimentalists).
This application can be started automatically when a new plot is created if the SCAN_DISPLAY variable is properly configured in the BLISS shell.

Flint listens to scan data source to know if there's something to display. The chart type (*curve*, *scatter plot*, *image*...) is automatically determined using the shape of the data. The data display is updated in real time as it is created.

```python
SCAN_DISPLAY.auto=True

timescan(0.1, lima, diode, diode2, simu1.counters.spectrum_det 0, npoints=10)

Activated counters not shown: spectrum_det0, image

Scan 145 Wed Apr 18 11:24:06 2018 /tmp/scans/ test_session user = matias
timescan 0.1

       #         dt(s)        diode2         diode
       0     0.0219111       12.5556      -9.33333
       1      0.348005        30.625         0.125
       2      0.664058       2.88889      -10.2222
       3      0.973582       7.11111       8.44444
       4       1.28277       21.7778       36.3333
       5       1.59305      -15.8889             5
       6       1.90203       43.4444       19.4444
       7       2.21207       20.7778       11.6667
       8       2.52451      -7.88889       24.2222
       9       2.83371        24.125         7.625

Took 0:00:03.214453
```

Flint screenshot:

![Flint screenshot](img/flint_screenshot.png)




[1]: http://silx.org