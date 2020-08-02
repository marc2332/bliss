
# For scan designers

Flint supports several metadata to improve the plot rendering.

This informations have to be known and defined at the build step of the scan.

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

- For `curve/scatter`
    - `start` (float): Start position of the axis
    - `stop` (float): Stop position of the axis
    - `min` (float): Minimal value the channel can have
    - `max` (float): Maximal value the channel can have
    - `points` (int): Amount of total points which will be transmitted by this
                      channel. It is used to compute the scan progress. And it
                      could be used to optimize memory allocation.
- For `scatter`
    - `axis-points` (int): Amount of points for the axis (see scatter below)
    - `axis-kind` (string): Kind of axis. It can be one of:
        - `forth`: For an axis always starting from start to stop
        - `backnforth`: For an axis which goes forth, increment the slower axis
                        and then goes back
        - `step`: For extra dimensions for axis which have discrete position
    - `axis-points` (int): Amount of axis points contained in the channel.
                           For scatter this amount of points will differ from
                           the amount of point owned by the same row, or column.
    - `axis-id` (int): Interleaved position of the axis in the scatter.
                       Smaller is faster. `0` is the fastest.
    - `axis-points-hint` (int): Used for irregular scatters. Flint will use it
                                to display this scatter as an 2D histogram.
                                This hint became the number of bins to use
                                (number of pixels)
- For any kind
    - `group` (string): Specify a group where the channel belong. All the
                        channels from the same group are supposed to contain the
                        same amount of elements at the end of the scan. It also
                        can be used as a hint to help interactive user selection.
                        If nothing is set, Flint will group the channel using
                        it's top master channel name from the acquisition chain.

Unsupported keys will not be used, and Flint will warn about it in the logs.

## Curve rendering

Right now this features is not used to display the curves. But it will be
done at one point.

- `min/max` will be used to constraint the default displayed view.
- `start/end` will be also used to constrain the displayed view.

Then `min` and `max` should be set close to the real data which will be provided
by the channel. Using theoretical range of an axis is not a good idea.

## Scatter rendering

This can be used for general cases of scatters

- `start/end/min/max` are used to constrain the default displayed view. This way
  the full data range can be visible from the beginning to the end of the
  acquisition without rescaling every time a new data is received.

Other metadata are used to optimize the solid rendering of the scatter. This
can reduce the CPU constraints and avoid blinking of the display.

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

# Examples

For example which can be used in BLISS shell, you can take a look at
[scan_info examples](flint_scan_info_examples.md).
