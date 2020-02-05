# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""PEPU hardware tests.

Run with:

    $ pytest -c /dev/null tests/controllers_hw/pepu.py -v \
    --cov bliss.controllers.pepu --cov-report html --cov-report term

"""

# Imports

from functools import partial
from contextlib import contextmanager

from unittest import mock
import pytest

from bliss.controllers.pepu import PEPU, Signal, Trigger


# Helpers


@contextmanager
def pepu_assert_command(pepu, write, read):
    conn = pepu.conn
    conn._write.reset_mock()
    conn._readline.reset_mock()
    conn._readline.return_value = read.encode()
    try:
        yield mock
        conn._write.assert_called_once_with(write.encode() + b"\n")
        conn._readline.assert_called_once()
    finally:
        conn._write.reset_mock()
        conn._readline.return_value = None
        conn._readline.reset_mock()


@contextmanager
def pepu_assert_block(pepu, n, name="TEST"):
    conn = pepu.conn
    cmd = "?*DSTREAM %s READ %d" % (name, n)
    with pepu.assert_command(cmd, "?*DSTREAM"):
        header = b"\x01\x00\xa5\xa5"
        header += b"\x00\x00\x00\x00"
        header += b"\x00\x00\x00\x00"
        binary = b"\x80\x01\x00\x00\x00\x00\x00\x00"
        binary += b"\x80\xfe\xff\xff\xff\xff\x00\x00"
        values = [header, binary * n]
        conn._read.side_effect = lambda *args, **kwargs: values.pop(0)
        try:
            yield mock
            assert pepu.conn._read.call_count == 2
        finally:
            conn._read.side_effect = None
            conn._read.reset_mock()


# Fixtures


@pytest.fixture
def pepu():
    with mock.patch("bliss.controllers.pepu.get_comm", autospec=True) as get_comm:
        pepu = PEPU("test", {"tcp": {"url": "pepudcm2"}})
        pepu.assert_block = partial(pepu_assert_block, pepu)
        pepu.assert_command = partial(pepu_assert_command, pepu)
        get_comm.assert_called_once_with(
            {"tcp": {"url": "command://pepudcm2:5000"}}, "tcp", eol="\n"
        )
        try:
            pepu.calc_channels[1].formula = "1.5"
            pepu.calc_channels[2].formula = "-1.5"
            pepu.out_channels[7].source = pepu.calc_channels[1].name
            pepu.out_channels[8].source = pepu.calc_channels[2].name
            yield pepu
        finally:
            pepu.conn.close()


# Tests


def test_simple_connection(pepu):
    with pepu.assert_command("?APPNAME", "PEPU"):
        assert pepu.app_name == "PEPU"

    with pepu.assert_command("?VERSION", "00.01"):
        assert pepu.version == "00.01"

    with pepu.assert_command("?DINFO", "UPTIME: BLI\nUNAME: BLA"):
        uptime, uname = pepu.dance_info.splitlines()
        assert uptime.startswith("UPTIME")
        assert uname.startswith("UNAME")

    with pepu.assert_command("?DCONFIG", "# %APPNAME% PEPU\n BLABLABLA"):
        assert pepu.config.startswith("# %APPNAME% PEPU")


@pytest.mark.parametrize("channel_id", list(range(1, 7)))
def test_read_in_channels(pepu, channel_id):
    cmd = "?CHVAL IN%d" % channel_id
    with pepu.assert_command(cmd, "-1.2"):
        channel = pepu.in_channels[channel_id]
        assert channel.value == -1.2


@pytest.mark.parametrize("channel_id", [7, 8])
def test_read_out_channels(pepu, channel_id):
    cmd = "?CHVAL OUT%d" % channel_id
    with pepu.assert_command(cmd, "-1"):
        channel = pepu.out_channels[channel_id]
        value = channel.value
    pytest.xfail()
    assert value in (1.5, -1.5)


@pytest.mark.parametrize("channel_id", [1, 2])
def test_read_calc_channels(pepu, channel_id):
    cmd = "?CHVAL CALC%d" % channel_id
    with pepu.assert_command(cmd, "-1"):
        channel = pepu.calc_channels[channel_id]
        value = channel.value
    pytest.xfail()
    assert value in (1.5, -1.5)


@pytest.mark.parametrize("acquisitions", [1, 2, 10])
@pytest.mark.parametrize("blocks", [1, 2, 10])
@pytest.mark.parametrize("block_size", [1, 2, 10])
def test_streams_acquisition(beacon, pepu, acquisitions, blocks, block_size):

    # Mocking
    command = "?DSTREAM TEST"
    return_value = "TEST OFF GLOBAL TRIG SOFT SOFT FSAMPL 10HZ NSAMPL {} SRC CALC1 CALC2".format(
        blocks * block_size
    )

    # Create stream
    pepu.conn._readline.return_value = return_value.encode()
    stream = pepu.create_stream(
        name="TEST",
        trigger=Trigger(Signal.SOFT, Signal.SOFT),
        frequency=10,
        nb_points=blocks * block_size,
        sources=("CALC1", "CALC2"),
        overwrite=True,
    )

    # General testing

    assert stream.name == "TEST"
    with pepu.assert_command(command, return_value):
        assert stream.trigger == Trigger(Signal.SOFT, Signal.SOFT)
    with pepu.assert_command(command, return_value):
        assert stream.frequency == 10
    with pepu.assert_command(command, return_value):
        assert stream.nb_points == blocks * block_size
    with pepu.assert_command(command, return_value):
        assert stream.sources == ["CALC1", "CALC2"]

    # Loop over acquisitions
    for _ in range(acquisitions):
        pepu.conn._readline.return_value = ""

        with pepu.assert_command("#DSTREAM TEST APPLY", "ACK IS NOT CHECKED"):
            stream.start()

        # Loop over blocks
        for _ in range(blocks):

            # Loop over points
            for _ in range(block_size):
                with pepu.assert_command("#STRIG", "ACK IS NOT CHECKED"):
                    pepu.software_trigger()

            # Read nb points
            with pepu.assert_command("?DSTREAM TEST NSAMPL", str(block_size)):
                assert stream.nb_points_ready == block_size

            # Read data
            with pepu.assert_block(block_size):
                data = stream.read(n=block_size)

            # Test
            assert data["CALC1"].tolist() == [1.5] * block_size
            assert data["CALC2"].tolist() == [-1.5] * block_size
