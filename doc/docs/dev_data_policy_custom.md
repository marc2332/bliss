# Custom data policy

SCAN_SAVING is a `ParametersWardrobe` which defines the data policy in the BLISS session. The activate data policy is selected in the session object (see `bliss/common/session.py`):

```python
class Session:

    def _set_scan_saving_class(self, scan_saving_class):
        scan_saving.set_scan_saving_class(scan_saving_class)
        self.scan_saving = scan_saving.ScanSaving(self.name)
        if is_bliss_shell():
            self.env_dict["SCAN_SAVING"] = self.scan_saving
```

Creating a custom data policy means deriving a class from `bliss.scanning.scan_saving.BaseScanSaving`:

```python

class CustomScanSaving(BaseScanSaving):
    DEFAULT_VALUES = {
        # default and not removable values
        "technique": "",
        ...
        # saved properties in Redis:
        "_proposal": "",
        ...
    }

    # read only attributes implemented with python properties
    PROPERTY_ATTRIBUTES = [
        "proposal",
        ...
    ]
    REDIS_SETTING_PREFIX = "custom_scan_saving"

    SLOTS = ["_custom_attr"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._custom_attr = None

    def get(self):
        try:
            # calculate all parameters
        except KeyError as keyname:
            raise RuntimeError("Missing %s attribute in CustomScanSaving" % keyname)
```
