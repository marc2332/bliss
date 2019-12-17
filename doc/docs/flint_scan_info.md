
# For scan designers

Flint supports several, metadata to improve the plot rendering.

This informations have to be fixed and known at the build step of the scan.

The default scan commands provide this metadata, but if you create your own
scans, you have to feed useful information on your own.

# Mecanism

The `scan_info` dictionary allow you to add extra information to a scan.

The `requests` field is used to register information attach to channels to Flint.

Here is an example to register few metadata to a channel named `my_channel`:
```
requests = {}
requests[f"my_channel"] = {
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

# List of supported metadata

Everything is optional, but have to be well typed.

- `start` (float): Start position of the axes
- `stop` (float): Stop position of the axes
- `min` (float): Minimal value the channel can have
- `max` (float): Minimal value the channel can have
- `points` (integer): Amount of total points which will be transmited by this channel
- `axes-points` (integer): Amount of points for the axes (see scatter below)
- `axes-kind` (string): Kind of axes (see scatter below)

Unsupported keys will not be used, and Flint will warn about it in the logs.

# General

- `points`: It is used to compute the scan progress. And could be used to
  optimize memory allocation.

# Curve rendering

Right now this features is not used to display the curves. But it will be
done at one point.

- `min/max` will be used to contraint the default displayed view.
- `start/end` will be also used to constrain the displayed view.

Then `min` and `max` should be set close to the real data which will contain the
channel. Using the theorical range of an axes here is not a good idea.

# Scatter rendering

This can be used for general cases of scatters

- `start/end/min/max` are used to contraint the default displayed view. This way
  the full data range can be visible from the beginning to the end of the
  acquisition without rescaling everytime a new data is received.

This can be used for regular mesh. A mesh is regular when you can find a row
and a column for each points of the scatter (n×m).

- `start/end` are also used to speed up solid rendering of scatters. It is used
  to know the orientation of the axes and then to compute a polygon mesh.
- `axes-points`: Amount of axes points contained in the channel. For scatter axes,
  the amount of points will differ from the amount of point owned by the same row,
  or column. This is the expected information here.
- `axes-kind`: Can be `slow` or `fast`. It is also used to speed up solid rendering.

## Example

Data for a regular scatter for axes `A` and `B` of 2×3 points will be received
following this pattern:

- `A0B0`, `A1B0`, `A0B1`, `A1B1`, `A0B2`, `A1B2`

- Then the `A` axes is the fast axes.
- The `B` axes is the slow axes (it is important to describe it too).
- The number of points for axes `A` is 2
- The number of points for axes `B` is 3

```
requests = {}
requests["A"] = {"axes-kind": "fast", "axes-points": 2, "points": 6}
requests["B"] = {"axes-kind": "slow", "axes-points": 3, "points": 6}
scan_info["requests"] = requests
```
