# Testing and BLISS

!!!note

    Doc partialy taken from `pytest` official doc: https://docs.pytest.org/en/latest/




## Running tests on your own computer



### Test setup

* Create a conda environment (named `testenv`) dedicated to tests

```
conda create --name testenv \
  --channel esrf-bcu --channel defaults --channel tango-controls --channel conda-forge \
  --file requirements-conda.txt  --file requirements-test-conda.txt
source activate testenv
```

* Go to BLISS source directory and do:

```
pip install --no-deps -e .
```


In the environment `testenv`:

* start a `BEACON` server using the provided _test_configuration_
(path relative to root of bliss repository)

```shell
beacon-server --db_path=....bliss/tests/test_configuration/ --webapp_port=9030 --posix_queue=0 --port=25000 --redis_port=25001 --tango_port=20000 --log-server-port=9020 --log-viewer-port=9080
```


### To run ALL tests

In BLISS root directory:

```
pytest
```

example of run (can be long):

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



### To run ONLY some tests



* To run a single test (`test_lima_ctrl_params_uploading`):
    - `-s`: keep stdout, equivalent to `--capture=no`  => do not capture stdout
    - `-v`: more verbose
    - `-q`: less verbose
    - `--count=20`: to repeat the test 20 times (`pytest-repeat` module must be installed)

```shell
pytest -sv --count=20  tests/controllers_sw/test_lima_simulator.py::test_lima_ctrl_params_uploading
```


* To run a set of tests

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


### other usages

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


!!! note
    To run Nexus writer test, use:
    `pytest tests/nexus_writer/ --durations=30 -m writer --runwritertests`










## Tests and Continuous Integration

All tests but hardware-related ones are automatically run during
continuous integration on *bcu-ci* server.


### To run tests on bcu-ci computer

Some timing problems occuring during continuous integration but not on
a local computer have been observed.

To track them, it can be interesting to run tests on `bcu-ci` computer.

Log-in to bcu-ci (needs sudo rights) and copy/paste:

```
sudo docker run -it continuumio/miniconda3:latest

apt-get update && apt-get -y install xvfb libxi6 git

git clone https://gitlab.esrf.fr/bliss/bliss.git

conda config --env --add channels conda-forge
conda config --env --append channels defaults
conda config --env --append channels esrf-bcu
conda config --env --append channels tango-controls

cd bliss

conda create -y --name testenv --file requirements-conda.txt --file requirements-test-conda.txt

source activate testenv

python setup.py install

pytest setup.py tests
```




## Tests configuration and creation


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
* `session`: to run tests within a BLISS session
* `log_context`: allows to get access to logging mechanisms
    - results are readable via `caplog` module
* other examples: `lima_simulator`, `dummy_tango_server`, `wago_tango_server`

#### session

`session` fixture gives access to `test_session` Bliss session:

* config

```python

def test_SampCnt_statistics(session):
    diode = session.config.get("diode")
    diode2 = session.config.get("diode2")
```


* env_dict

```python
def test_SampCnt_mode_SINGLE(session):
    env_dict = session.env_dict

    diode2 = env_dict["diode2"]
    diode8 = env_dict["diode8"]
```

* `config_app_port`
* `homepage_app_port`
* `beacon_tmpdir`
* `beacon_directory`
* `log_directory`
* `images_directory`
* ports:
    - `redis_port`
    - `redis_data_port`
    - `tango_port`
    - `beacon_port`
    - `cfgapp_port`
    - `logserver_port`
    - `homepage_port`


#### capsys

`capsys` fixture gives access to the standard output and error.


example:
```
def test_bench(beacon, setup_globals, capsys):
    with bench():
        gevent.sleep(1)

    captured = capsys.readouterr()
    assert "Execution time: 1s" in captured.out
```

see also: `capsysbinary`, `capfd`, and `capfdbinary` fixtures.


#### Exceptions
To test that an exception is well reaise, `pytest.raises()` context manager can
be used. This test will *success* if a `ValueError` exception is raised:

```python
with pytest.raises(ValueError):
    mca.rois.set("Auguste", -63, 14)
```


#### approx

To test equality of floats or to test 2 values with an approximation margin,
`pytest.approx` must be used.

example to ensure that position is `6.28` more or less `0.001`:
```python
assert roby.position == pytest.approx(6.28, abs=1e-3)
```

!!! danger
    `rel` or `abs` keyword arg should be used to avoid mistake.
    ```
    In [38]: 111 == pytest.approx(112.0, 0.1)    # <--- !!! rel by default
    Out[38]: True
    
    In [39]: 111 == pytest.approx(112.0, abs=0.1)
    Out[39]: False
    ```

!!! danger
    `assert pytest.approx(position, 2)` is WRONG (compare position to nothing)
    use: `assert position == pytest.approx(2)`


see: https://docs.pytest.org/en/latest/reference.html#pytest-approx for details.


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


## pylint

Pylint is a tool that checks for errors in Python code. It can recommend
suggestions about how particular blocks can be refactored and can offer details
about the code's complexity.

`pylint` is ran automatically by the Continuous Integration pipeline before to
start `pytest`.

For now it triggers only warnings and is not lbocking in the CI process.

`pylint` produces logs that can be read on `gitlab` pipelines page. Clic on the
first orange icon in column `Stages`, then `check_lint` then at bottom of the
page comments like that can be read:

```
68 ../test_axis.py:25:1: F401 'log_shell_mode' imported but unused
69 ../test_axis.py:569:30: F811 redefinition of 'log_shell_mode' from line 25
```

These comments can usually be profitably followed. Some more or less tricky bugs
(typically typo on variable names) can then be avoided.


### pylint false positive

In (rare) case of false positive error detection, an indication to avoid warning
during CI can be added in the code.

For example, in `tests/motors/test_axis.py`, the `F401` reported error is wrong,
`log_shell_mode` is used.

To avoid warning, "` # noqa: F401`" comment has been added to the line `25`:

```python
from ..common.conftest import log_shell_mode  # noqa: F401
```
