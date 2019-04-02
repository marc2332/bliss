# BLISS releases...


NOTES for BLISS releasing.


file to update: `./bliss/release.py`

## Releases policy

### Releases policy proposition

* A new release is triggered by a need of a user ( bugfix, feature, new controller).
* user or BLISS core team make the needed code.
* user runs integration test(s) on beamline(s):
    * beamline specific
    * experiment specific ?
    * a generic test ?
* user gives feedback to BLISS core team if needed.
* BLISS core team creates a new release number:
    * releases have number of the form: VERSION.MAJOR.MINOR.PATCH
    * a release number is bind to a tag or a branch depending on the state of the git repo tree, but it's not visible from the user point of view.
        * BLISS official: VERSION number is increased
        * API change: MARJOR number is increased
        * new feature: MINOR number is increased
        * small bugfix or new controller with no changes in API or change needed in users codes : PATCH is increased
* if a backport of a bugfix is needed, the BLISS core team can create a branch or a new tag in the repo tree, but this is not visible to users.
* BLISS core team ensures that an upgrade of a minor version is safe :)
* BLISS core team will provide RELEASE_NOTES for each BLISS Conda package


## history

BLISS test packages (0.1.0 -> 0.1.3) are built from git repository at commit: 27733b06aa9ccfe99ad9f6bcf6810007cafdb8a9
