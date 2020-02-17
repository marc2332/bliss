# Flint interaction

In order to interact with a given plot, to choose points or regions of interest of different shapes, plot objects propose two methods : `select_point()` and `select_shape()`.

Exemple:

```python
from bliss.common.plot import *
import numpy

xx = numpy.linspace(0, 4*3.14, 50)
yy = numpy.cos(xx)

p = plot(yy, name="Plot 0")
p
         Out [10]: CurvePlot(plot_id=2, flint_pid=13678, name=u'')
```

Once that the plot `p` object is created (an `CurvePlot` in this case), several options are available to interact with the plot:

- ``select_points(pointnumber)`` : 
- ``select_shape(shape)`` where ``shape`` could be:
     - ``'rectangle'``: rectangle selection
     - ``'line'``: line selection
     - ``'hline'``: horizontal line selection
     - ``'vline'``: vertical line selection
     - ``'polygon'``: polygon selection

!!! note
     When selecting a ``polygon`` shape, click on the starting point of the polygon to close it (the polygon) and to return to BLISS shell.

Example:

`rectangle = p.select_shape("rectangle")`

BLISS shell is blocked until user makes a rectangular selection:

Once the rectangle is created, back on the BLISS shell, result is returned by the `select_shape` method:

```py
rectangle
Out [11]: [[278.25146, 716.00623], [623.90546, 401.82913]]
```

The ``select_points`` method allows the user to select a given number of point
on the corresponding plot using their mouse.

```python
a, b, c = p.select_points(3)
# Blocks until the user selects the 3 points
a
[1.2, 3.4]
```

The return values are shown in the following example:

```python
topleft, bottomright = p.select_shape('rectangle')
start, stop = p.select_shape('line')
left, right = p.select_shape('hline')
bottom, top = p.select_shape('vline')
points = p.select_shape('polygon')
```


