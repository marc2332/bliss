
# For scan designers

Flint supports several metadata to improve the plot rendering.

This informations have to be known and defined at the build step of the scan.

The default scan commands provide this metadata, but if you create your own
scans, you have to feed useful information on your own.

# Mechanism

The `scan_info` dictionary allows you to add extra information to a scan.

And a field `channels`, already feed by the `Scan` object is used to annotate
each channel with information. An helper is provided to feed this dictionary.
Better not to edit the dictionary manually.

# Global metadata

This metadata must be at the root of `scan_info`.

- `npoints` (int): Number of expected points for the scan.
- `npoints1` (int): Number of expected points of the first axis of a mesh scan
- `npoints2` (int): Number of expected points of the second axis of a mesh scan

That's one available option used Flint to compute a progress bar for a scan.

size per channels.

- `data_dim` (int): Dimensionality of the scan
- `dim` (int): Alias of `data_dim`

Flint uses this metadata to display the data as a scatter if equals to 2.

# Channel's metadata

Here is an example to update few metadata to a channel named `my_channel`:

```
from bliss.scanning.scan_info import ScanInfo
scan_info = ScanInfo()
# The channel name is a fullname
scan_info.set_channel_meta("my_channel_name", start=1, stop=2)

scan = Scan(
    chain,
    scan_info=scan_info,
    ...
)
```

## List of channel's metadata

Everything is optional, but have to be well typed.

Better to refer to the documentation of `ScanInfo.set_channel_meta` which is
probably up-to-date.

- For `curve/scatter`
    - `start` (float): Start position of the axis
    - `stop` (float): Stop position of the axis
    - `min` (float): Minimal value the channel can have
    - `max` (float): Maximal value the channel can have
    - `points` (int): Amount of total points which will be transmitted by this
                      channel. It is used to compute the scan progress. And it
                      could be used to optimize memory allocation.
- For `scatter`
    - `axis_points` (int): Amount of points for the axis (see scatter below)
    - `axis_kind` (string): Kind of axis. It can be one of:
        - `forth`: For an axis always starting from start to stop
        - `backnforth`: For an axis which goes forth, increment the slower axis
                        and then goes back
        - `step`: For extra dimensions for axis which have discrete position
    - `axis_points` (int): Amount of axis points contained in the channel.
                           For scatter this amount of points will differ from
                           the amount of point owned by the same row, or column.
    - `axis_id` (int): Interleaved position of the axis in the scatter.
                       Smaller is faster. `0` is the fastest.
    - `axis_points_hint` (int): Used for irregular scatters. Flint will use it
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

## Curve rendering

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

Plots can be described in the `scan_info`, and stored in the `plots` field.

If there is no plot description (the field is not there), Flint will try to infer
plots from other `scan_info` fields.

If this field is an empty list, Flint will consider that there is no plot to
display. This can be useful to ignore the content of a scan, like for example
a sequence of scans.

For now, very basic plots are supported for curves and scatters.

Here is an example.
```
from bliss.scanning.scan_info import ScanInfo
scan_info = ScanInfo()
scan_info.add_scatter_plot(name="unique-plot-name",
                           x="axis:sx",
                           y="axis:sy",
                           value="diode2")

scan_info.add_curve_plot(name="unique-plot-name2", x="axis:sx")
```

The default BLISS commands uses this API to specify the default channels to use
as axis for the curve and the scatter plots. In this case the plot name is not set,
cause it is considered as a default plot.

If you want to use standard scans, you can override this plot by defining the
default plot in the `scan_info` passed to the standard scan command. It will not
be redefined.

For your information in BLISS 1.9, the previous code will generate a dictionary
looking like the following one. But it is not recommended to generate it
manually, in case of changes.
```
plots = [
    {
        "name": "unique-plot-name"
        "kind": "scatter-plot",
        "items": [
            {"kind": "scatter", "x": "axis:sx", "y": "axis:sy", "value": "diode2"},
        ]
    },
    {
        "name": "unique-plot-name2"
        "kind": "curve-plot",
        "items": [
            {"kind": "curve", "x": "axis:sx"},
        ]
    },
]
```

# Examples

Few working examples are provided at
[scan_info examples](flint_scan_info_examples.md).

# Scan sequence

Metadata can also be added to the BLISS scan sequence in order
to make them understandable client side.

- `set_sequence_info` can be used to say how many scans are expected. This is
  used by Flint to display the progress of the sequence.
- A sub scan must added to the sequence before running. This is needed to
  provide parenting of the scans in Flint.

```
from bliss.scanning.group import Sequence
from bliss.scanning.scan_info import ScanInfo

flint()
scan_info = ScanInfo()
scan_info.set_sequence_info(scan_count=10)

seq = Sequence(scan_info=scan_info)
with seq.sequence_context() as scan_seq:
    for i in range(10):
        s = loopscan(10, 0.5, tomocam, run=False)
        scan_seq.add(s)
        s.run()
```
