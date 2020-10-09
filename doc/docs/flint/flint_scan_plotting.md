# Flint Scan Plotting

On BLISS, online data display relies on **flint**, a graphical application built
on top of [silx][1] (ScIentific Library for eXperimentalists).
This application can be started automatically when a new plot is created if the
`SCAN_DISPLAY` variable is properly configured in the BLISS shell.

Flint listens to scan data source to know if there's something to display.
The chart type (*curve*, *scatter plot*, *image*...) is automatically determined
using the kind of the data. The data display is updated in real time as it is
created.

## Curve widget

If the scan contains counters, the curve widget will be displayed automatically.

It will also be displayed mesh scans.

![Flint screenshot](img/flint-curve-widget.png)

This plot provides an API to [interact with region of interest](flint_interaction.md)
and to custom few things. The following lines shows how to add processed data from
BLISS shell.

```python
scan = ascan(sx,0,2,100,0.01, diode1, diode2)

# Denoise the signal from the diode1
import scipy.signal
ydata = scan.get_data()[diode1.fullname]
n = 15
b = [1.0 / n] * n
ydenoised = scipy.signal.lfilter(b, 1, ydata)

# Make sure flint is uptodate with the last scan
f.wait_end_of_scans()

# Get the live plot and attach the denoised signal to the diode1
p = f.get_live_plot("default-curve")
p.update_user_data("denoized", diode1.fullname, ydenoised)
```

## Scatter widget

If the scan contains counters data which have to be displayed is 2D, the
scatter widget will be displayed automatically.

That's the case for `mesh` scans.

![Flint screenshot](img/flint-scatter-widget.png)

## MCA widget

For scans containing MCAs data, the MCA widget will be displayed automatically.

A specific widget will be created per detector.

Only the last retrieved data will be displayed, so for a time scan you have to
create first ROIs on the MCAs to display data in time.

![Flint screenshot](img/flint-mca-widget.png)

## Image widget

For scans containing image data, the image widget will be displayed automatically.

A specific widget will be created per detector.

Only the last retrieved data will be displayed, so for a time scan you have to
create first ROIs on the MCAs to display data in time.

![Flint screenshot](img/flint-image-widget.png)

This plot provides an API to [interact with region of interest](flint_interaction.md)
and to custom the colormap, and few other things. This can be used in scripts.

```python
ct(tomocam)

# Make sure the scan was also completed in flint side
f = flint()
f.wait_end_of_scans()

p = f.get_live_plot(image_detector="tomocam")

p.set_colormap(lut="gray",
               vmin=0, vmax="auto",
               normalization="log",
               autoscale_mode="stddev3")

p.export_to_logbook()
```

## Count widget

For `ct` scans, the count widget will be automatically displayed.

![Flint screenshot](img/flint-count-widget.png)

## Positioners widget

Usually a scan contains information on the positioners, which is the location
of all the motors before and after the scan.

The positioners widget **can** be displayed. The 📜 `Windows` menu provides an
entry to show/hide this widget.

![Flint screenshot](img/flint-positioners-widget.png)

[1]: http://silx.org