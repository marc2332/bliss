# Testing BLISS

## Test setup

* Create a conda environment dedicated to tests

```
conda create --name testenv --channel esrf-bcu \
  --channel defaults --channel tango-controls --channel conda-forge \
  --file requirements-conda.txt  --file requirements-test-conda.txt
source activate testenv
```

* Go to BLISS source directory and do:

```
pip install --no-deps -e .
```

### Running BLISS test session

In the test environment: 

* start a BEACON server using the provided _test_configuration_ (path relative to root of bliss repository)

```shell
beacon-server --db_path tests/test_configuration/ --tango_port 20000
```

* Start test session device servers, like Lima camera simulators:

```shell
TANGO_HOST=localhost:20000 LimaCCDs simulator
```

* Start the BLISS shell:

```shell
BEACON_HOST=localhost TANGO_HOST=localhost:20000 bliss -s test_session
```

* A lot of controllers are already part of the test session. The ones depending on
a Tango server are not included by default, so those devices can be accessed via
the `config` object:

```python
TEST_SESSION[1]: limaDev = config.get("lima_simulator")
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

## Pytest

Partialy taken from `pytest` official doc: https://docs.pytest.org/en/latest/

### Usage in BLISS

All tests but hardware-related ones are automatically run during
continuous integration on *bcu-ci* server.

#### To run ALL tests

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

    In case of strange error (like `ImportError: bad magic number`),
    try to remove old `*.pyc` files:

    `find ./ -name "*.pyc" | xargs rm`


#### To run ONLY some tests

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

### Pytest command line options

* `-s`: keep stdout, equivalent to `--capture=no`  => do not capture stdout
* `-v`: more verbose
* `-q`: less verbose

### `xfail`

`pytest.xfail()` instruction

"A `xfail` means that you expect a test to fail for some reason. A common example
is a test for a feature not yet implemented, or a bug not yet fixed. When a test
passes despite being expected to fail (marked with pytest.mark.xfail), it’s an
xpass and will be reported in the test summary."

see: http://doc.pytest.org/en/latest/skipping.html

```
@pytest.mark.parametrize("channel_id", [1, 2])
def test_read_calc_channels(pepu, channel_id):
    cmd = "?CHVAL CALC%d" % channel_id
    with pepu.assert_command(cmd, "-1"):
        channel = pepu.calc_channels[channel_id]
        value = channel.value
    pytest.xfail()
    assert value in (1.5, -1.5)
```

### Coverage

Coverage indicates the percentage of lines touched by current tests suite.

Example to get a coverage report:

```bash
py.test tests/controllers_sw/test_multiple_positions.py   \
           --cov-report=html                              \
           --cov bliss.controllers.multiplepositions
```

Coverage report indicating tested lines is in:
  ./htmlcov/index.html

!!! note
    There can be some errors (lines tested but not flaged as tested) in the
    report.

See also: https://pytest-cov.readthedocs.io/en/latest/reporting.html


### Pytest configuration

Configuration is mainly done in `setup.cfg` file:

```
bliss %
bliss % more setup.cfg
   
   [tool:pytest]
   addopts = -v --ignore=tests/images --ignore=tests/test_configuration --ignore=tests/controllers_hw
   usefixtures = clean_louie clean_gevent clean_globals clean_tango
   filterwarnings =
       ignore::DeprecationWarning
       ignore::PendingDeprecationWarning
   
   [aliases]
   test=pytest
```

### Tips and examples

#### Fixtures

https://docs.pytest.org/en/latest/fixture.html


A set of fixtures is defined in `tests/conftest.py` file.

Their role is to ease the definition of tests by factorizing some procedures.

Examples:

* `beacon`: to give access to the configuration in the test function via `config`
* `session`: to run testss within a BLISS session
* `log_context`: allows to get access to logging mechanisms
    - results are readable via `caplog` module
* other examples: `lima_simulator`, `dummy_tango_server`, `wago_tango_server`

#### capsys

`capsys` module gives access to the standard output and error.

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

#### Access to temporary directory

```python
def test_session_add_del(beacon, beacon_directory):
    # beacon_directory is the temporary directory used by tests.
    # BLISS Session files are put in beacon_directory/sessions
    sess_dir = beacon_directory + '/sessions'
    setup_file = sess_dir + '/tutu_setup.py'
```

## Hardware tests

Tests files located in `bliss/tests/controllers_hw/` directory are *Hardware tests*.
They are ignored by continuous integration but can be run manualy.

!!! warning
    They are using the beamline database for configuration and not the test
    configuration.

### Axis

There is a generic axis test for basic feature: position, velocity, acceleration
and stop.

Example:
```
pytest -s --axis-name rot tests/controllers_hw/test_axis.py
```
This will do a real test on *Beamline* axis named **rot**.

!!! warning
    This test will do real movement on the specified axis.


