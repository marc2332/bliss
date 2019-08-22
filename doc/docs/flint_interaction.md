
# Flint interaction

In order to interact with a given plot, several methods are provided.

The ``select_points`` method allows the user to select a given number of point
on the corresponding plot using their mouse.

```python
a, b, c = p.select_points(3)
# Blocks until the user selects the 3 points
a
(1.2, 3.4)
```

The ``select_shape`` methods allows the user to select a given shape on the
corresponding plot using their mouse. The available shapes are:

- ``'rectangle'``: rectangle selection
- ``'line'``: line selection
- ``'hline'``: horizontal line selection
- ``'vline'``: vertical line selection
- ``'polygon'``: polygon selection

The return values are shown in the following example:

```python
topleft, bottomright = p.select_shape('rectangle')
start, stop = p.select_shape('line')
left, right = p.select_shape('hline')
bottom, top = p.select_shape('vline')
points = p.select_shape('polygon')
```


