
# For scan designers

Flint supports several metadata to improve the plot rendering.

This informations have to be fixed and known at the build step of the scan.

The default scan commands provide this metadata, but if you create your own
scans, you have to feed useful information on your own.

# Mechanism

The `scan_info` dictionary allows you to add extra information to a scan.

A field `requests` can be provided to `scan_info` to annotate each channel with
information.

# Global metadata

This metadata must be at the root of `scan_info`.

- `npoints` (int): Number of expected points for the scan.
- `npoints1` (int): Number of expected points of the first axis of a mesh scan
- `npoints2` (int): Number of expected points of the second axis of a mesh scan

Flint can compute a progress bar for the scan using this information. If the
channels do not have the same size, you can use `requests` to specify the expected
size per channels.

- `data_dim` (int): Dimensionality of the scan
- `dim` (int): Alias of `data_dim`

Flint uses this metadata to display the data as a scatter if equals to 2.

# Request metadata

Here is an example to register few metadata to a channel named `my_channel`:
```
requests = {}
requests["my_channel"] = {
    "start": 1,
    "stop": 2,
}

scan_info = {}
scan_info["requests"] = requests

scan = Scan(
    chain,
    scan_info=scan_info,
    ...
)
```

An helper is provided to simplify the creation of your `scan_info`. The
following code is the exact same as the previous one. It is recommended to use
this way.

```
scan_info = {}

from bliss.commons.scans.scan_info import ScanInfoBuilder
builder = ScanInfoBuilder(scan_info)
builder.set_channel_meta("my_channel", start=1, stop=2)

scan = Scan(
    chain,
    scan_info=scan_info,
    ...
)
```

## List of `requests` metadata

Everything is optional, but have to be well typed.

- `start` (float): Start position of the axis
- `stop` (float): Stop position of the axis
- `min` (float): Minimal value the channel can have
- `max` (float): Minimal value the channel can have
- `points` (integer): Amount of total points which will be transmitted by this
                      channel.
- `axis-points` (integer): Amount of points for the axis (see scatter below)
- `axis-kind` (string): Kind of axis (see scatter below)
- `group` (string): Specify a group where the channel belong. All the channels
                    from the same group are supposed to contain the same amount
                    of elements at the end of the scan. It also can be used as
                    a hint to help interactive user selection.
                    If nothing is set, Flint will group the channel using it's
                    top master channel name from the acquisition chain.

Unsupported keys will not be used, and Flint will warn about it in the logs.

## General case

- `points`: is used to compute the scan progress. And it could be used to
  optimize memory allocation.

## Curve rendering

Right now this features is not used to display the curves. But it will be
done at one point.

- `min/max` will be used to constraint the default displayed view.
- `start/end` will be also used to constrain the displayed view.

Then `min` and `max` should be set close to the real data which will be provided
by the channel. Using theoretical range of an axis is not a good idea.

## Scatter rendering

This can be used for general cases of scatters

- `start/end/min/max` are used to constraint the default displayed view. This way
  the full data range can be visible from the beginning to the end of the
  acquisition without rescaling every time a new data is received.

This can be used for regular mesh. A mesh is regular when you can find a row
and a column for each points of the scatter (n×m).

- `start/end` are also used to speed up solid rendering of scatters. It is used
  to know the orientation of the axis and then to compute a polygon mesh.
- `axis-points`: Amount of axis points contained in the channel. For scatter axes,
  the amount of points will differ from the amount of point owned by the same row,
  or column.
- `axis-kind`: Can be one of `fast`, `fast-backnforth` or `slow`.
  It is also used to speed up solid rendering.

## Scatter example

Data for a regular scatter for axes `A` and `B` of 2×3 points will be received
following this pattern:

- `v(A0, B0)`, `v(A1, B0)`, `v(A0, B1)`, `v(A1, B1)`, `v(A0, B2)`, `v(A1, B2)`

- Then the `A` axis is the fast axis.
- The `B` axis is the slow axis (it is important to describe it too).
- The number of points for axis `A` is 2
- The number of points for axis `B` is 3

```
requests = {}
requests["A"] = {"axis-kind": "fast", "axis-points": 2, "points": 6}
requests["B"] = {"axis-kind": "slow", "axis-points": 3, "points": 6}
scan_info["requests"] = requests
```

# Plot description

Plots can be described in the `scan_info`.

If there is no plot description, Flint will try to infer plots from other
`scan_info` fields.

It is stored in the `plots` field.

For now only scatters are supported.

Here is an example.
```
plots = [
    {
        "name": "unique-plot-name"
        "kind": "scatter-plot",
        "items": [
            {"x": "axis:sx", "y": "axis:sy", "value": "diode2"},
        ]
    },
]
```

The plot name is not mandatory. It will be used by Flint to reuse the same plot
widget between scans. A single plot without name will use the default scatter
plot provided by Flint.

An helper is provided to simplify the creation of your `scan_info`. It is
recommended to use it.

```
scan_info = {}

from bliss.commons.scans.scan_info import ScanInfoBuilder
builder = ScanInfoBuilder(scan_info)
builder.add_scatter_plot(name="unique-plot-name",
                         x="axis:sx",
                         y="axis:sy",
                         value="diode2")
```
