"""PEPU hardware tests.

Run with:

    $ pytest -c /dev/null tests/controllers_hw/pepu.py -v \
    --cov bliss.controllers.pepu --cov-report html --cov-report term

"""

import pytest

from bliss.common import scans
from bliss.controllers.pepu import PEPU, Signal, Trigger, ChannelMode

pytestmark = pytest.mark.pepu


@pytest.fixture
def pepu(request):
    hostname = request.config.getoption("--pepu")
    pepu = PEPU("test", {"tcp": {"url": hostname}})
    try:
        pepu.calc_channels[1].formula = "1.5"
        pepu.calc_channels[2].formula = "-1.5"
        pepu.out_channels[7].source = pepu.calc_channels[1].name
        pepu.out_channels[8].source = pepu.calc_channels[2].name
        yield pepu
    finally:
        pepu.conn.close()


def test_simple_connection(pepu):
    assert pepu.app_name == "PEPU"
    assert pepu.version == "00.01"
    assert pepu.up_time > 0
    assert pepu.sys_info.startswith("DANCE")
    uptime, uname = pepu.dance_info.splitlines()
    assert uptime.startswith("UPTIME")
    assert uname.startswith("UNAME")
    assert pepu.config.startswith("# %APPNAME% PEPU")


@pytest.mark.parametrize("channel_id", list(range(1, 7)))
def test_read_in_channels(pepu, channel_id):
    channel = pepu.in_channels[channel_id]
    assert channel.value in [-1., 0.]


@pytest.mark.parametrize("channel_id", list(range(1, 7)))
def test_in_channel_config(pepu, channel_id):
    channel = pepu.in_channels[channel_id]

    # test state
    enabled = channel.enabled
    assert channel.enabled is True or channel.enabled is False

    # disabled the state
    channel.enabled = False
    assert channel.enabled is False

    # test mode
    mode = channel.mode
    assert channel.mode in tuple(ChannelMode)

    channel.mode = ChannelMode.BISS
    assert channel.mode == ChannelMode.BISS


@pytest.mark.parametrize("channel_id", [7, 8])
def test_read_out_channels(pepu, channel_id):
    channel = pepu.out_channels[channel_id]
    value = channel.value
    pytest.xfail()
    assert value in (1.5, -1.5)


@pytest.mark.parametrize("channel_id", [1, 2])
def test_read_calc_channels(pepu, channel_id):
    channel = pepu.calc_channels[channel_id]
    value = channel.value
    pytest.xfail()
    assert value in (1.5, -1.5)


@pytest.mark.parametrize("acquisitions", [1, 2, 10])
@pytest.mark.parametrize("blocks", [1, 2, 10])
@pytest.mark.parametrize("block_size", [1, 2, 10])
def test_streams_acquisition(pepu, acquisitions, blocks, block_size):
    # Create stream
    stream = pepu.create_stream(
        name="TEST",
        trigger=Trigger(Signal.SOFT, Signal.SOFT),
        frequency=10,
        nb_points=blocks * block_size,
        sources=("CALC2", "CALC1"),
        overwrite=True,
    )
    # Argument testing
    assert stream.name == "TEST"
    assert stream.trigger == Trigger(Signal.SOFT, Signal.SOFT)
    assert stream.frequency == 10
    assert stream.nb_points == blocks * block_size
    assert stream.sources == ["CALC1", "CALC2"]
    assert not stream.active
    # Loop over acquisitions
    for _ in range(acquisitions):
        stream.start()
        # Loop over blocks
        for _ in range(blocks):
            # Loop over points
            for _ in range(block_size):
                pepu.software_trigger()
            # Read block
            assert stream.nb_points_ready == block_size
            data = stream.read(n=block_size)
            assert data["CALC1"].tolist() == [1.5] * block_size
            assert data["CALC2"].tolist() == [-1.5] * block_size


def test_timescan(pepu):
    scan = scans.timescan(
        0.1,
        pepu.counters.CALC1,
        pepu.counters.CALC2,
        npoints=3,
        return_scan=True,
        save=False,
    )
    data = scan.get_data()
    assert data["CALC1"].tolist() == [1.5] * 3
    assert data["CALC2"].tolist() == [-1.5] * 3
