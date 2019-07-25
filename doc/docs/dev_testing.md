# Testing with PyTest


Partialy taken from `pytest` official doc: https://docs.pytest.org/en/latest/


## Usage in BLISS

All tests but hardware-related ones are automatically run during
continuous integration on *bcu-ci* server.

### To run manually ALL tests

In BLISS root directory:

```
pytest
```

example to run all tests (can be long):

```
bliss % pytest
========================== test session starts ==============================
[...]
collected 454 items

tests/test_channels.py::test_channel_not_initialized PASSED            [  0%]
tests/test_channels.py::test_channel_set PASSED                        [  0%]
tests/test_channels.py::test_channel_cb PASSED                         [  0%]
[...]
```


!!! note

    In case of strange error (like `ImportError: bad magic number`), try to remove old `*.pyc` files:
    
    `find ./ -name "*.pyc" | xargs rm`


### to run ONLY some tests

In BLISS root directory:
```
pytest -k <sub-string>
```

`-k` command line option specify an expression which implements a
sub-string match on the test names instead of the exact match on
markers that `-m` provides.

example :

```
bliss % pytest  -k channel_not_initialized
============================= test session starts =============================
[...]
collected 454 items / 453 deselected

tests/test_channels.py::test_channel_not_initialized PASSED              [100%]

====================== 1 passed, 453 deselected in 5.15 seconds ===============
```

### Main options

#### -s: keep stdout
Equivalent to `--capture=no`  => do not capture stdout

#### -v: more verbose

#### -q: less verbose


## Hardware tests

Hardware tests are ignored by continuous integration but can be run manualy.

!!! warning
    They are using the beamline database for configuration and not the test
    configuration.

### Axis
The is a generic axis test for basic feature: position, velocity, acceleration and stop.

Example:
```
pytest -s --axis-name rot tests/controllers_hw/test_axis.py
```
This will do a real test on *Beamline* axis named **rot**.

!!! warning
    This test will do real movement on the specified axis.


## Configuration in BLISS
Configuration is mainly done in `setup.cfg` file:

```
bliss %
bliss % more setup.cfg
   
   [tool:pytest]
   addopts = -v --ignore=tests/images --ignore=tests/test_configuration --ignore=tests/controllers_hw
   usefixtures = clean_louie clean_gevent clean_session
   filterwarnings =
       ignore::DeprecationWarning
       ignore::PendingDeprecationWarning
   
   [aliases]
   test=pytest
```



## Writing tests

TODO

### Tips and examples

#### Using a Tango device server in tests

A dummy tango device server is defined in :

`tests/test_configuration/tango/dummy.yml`

```yaml
device:
- class: Dummy
  tango_name: id00/tango/dummy
  personal_name: dummy
  server: dummy_tg_server
```

It is used for example to test undulator object:

config:
```yaml
controller:
    class: ESRF_Undulator
    ds_name: id00/tango/dummy
    axes:
        -
            name: u23a
            attribute_position: Position
            attribute_velocity: Velocity
            attribute_acceleration: Acceleration
            steps_per_unit: 1
            velocity: 5
            acceleration: 125
            tolerance: 0.1
```

test:
```python
import pytest
def test_undulator(beacon, dummy_tango_server):
    u23a = beacon.get("u23a")

    assert u23a.position == 1.4
    assert u23a.velocity == 5
    assert u23a.acceleration == 125
```

#### acces to temporary directory

```python
def test_session_add_del(beacon, beacon_directory):
    # beacon_directory is the temporary directory used by tests.
    # BLISS Session files are put in beacon_directory/sessions
    sess_dir = beacon_directory + '/sessions'
    setup_file = sess_dir + '/tutu_setup.py'
```

## Installation

### to run tests on your computer


* Create a conda environemnt dedicated to tests:
    * Go to bliss directory and do:
```
conda create --name testenv --channel http://bcu-ci.esrf.fr/stable \
  --channel defaults --channel tango-controls --channel conda-forge \
  --file requirements-conda.txt  --file requirements-test-conda.txt
source activate testenv
pip install .
```
    * Install bliss:
```
cd bliss.git/
pip install --no-deps -e .
```

### to run tests on bcu-ci computer

Some timing problems occuring during continuous integration but not on
a local computer have been observed.

To track them, it can be interesting to run tests on `bcu-ci` computer.

Log-in to bcu-ci (needs sudo rights) and copy/paste:

```
sudo docker run -it continuumio/miniconda3:latest

apt-get update && apt-get -y install xvfb libxi6 git

git clone https://gitlab.esrf.fr/bliss/bliss.git

cd bliss

conda create -y --name testenv --channel http://bcu-ci.esrf.fr/stable  \
  --channel defaults --channel tango-controls --channel conda-forge \
  --file requirements-conda.txt  --file requirements-test-conda.txt

source activate testenv

python setup.py install

pytest setup.py tests
```

Happy debugging !


