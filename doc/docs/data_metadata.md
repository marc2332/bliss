Detectors publish their own metadata by default. Here we describe how to add user metadata. A more flexible and presistent way to add metadata is described [here](data_metadata_dev.md).

## E-logbook
Send user message to the [e-logbook](https://data.esrf.fr)

```
DEMO  [1]: lprint("user message in electronic logbook ")
```

## Scan comments
Add comments to your scans

```python
DEMO [1]: s = loopscan(10,0.1,run=False)
DEMO [2]: s.add_comment("This is a comment")
DEMO [3]: s.add_comment("This is another comment")
DEMO [4]: s.add_comment("And another one")
DEMO [4]: s.run()
```