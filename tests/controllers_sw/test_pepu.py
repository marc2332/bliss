"""PEPU hardware tests.

Run with:

    $ pytest -c /dev/null tests/controllers_hw/pepu.py -v \
    --cov bliss.controllers.pepu --cov-report html --cov-report term

"""

import mock
import pytest

from bliss.controllers.pepu import PEPU, Signal, Trigger


@pytest.fixture
def pepu():
    with mock.patch('bliss.controllers.pepu.get_comm') as get_comm:
        pepu = PEPU('test', {'tcp': {'url': 'pepudcm2'}})
        get_comm.assert_called_once_with(
            {'tcp': {'url': 'command://pepudcm2:5000'}}, 'tcp', eol='\n')
        try:
            pepu.calc_channels[1].formula = '1.5'
            pepu.calc_channels[2].formula = '-1.5'
            pepu.out_channels[7].source = pepu.calc_channels[1].name
            pepu.out_channels[8].source = pepu.calc_channels[2].name
            yield pepu
        finally:
            pepu.conn.close()


def test_simple_connection(pepu):
    pepu.conn._readline.return_value = 'PEPU'
    assert pepu.app_name == 'PEPU'

    pepu.conn._readline.return_value = '00.01'
    assert pepu.version == '00.01'

    pepu.conn._readline.return_value = "3.4"
    assert pepu.up_time == 3.4

    pepu.conn._readline.return_value = 'DANCE BLABLABLA'
    assert pepu.sys_info.startswith('DANCE')

    pepu.conn._readline.return_value = 'UPTIME: BLI\nUNAME: BLA'
    uptime, uname = pepu.dance_info.splitlines()
    assert uptime.startswith('UPTIME')
    assert uname.startswith('UNAME')

    pepu.conn._readline.return_value = '# %APPNAME% PEPU\n BLABLABLA'
    assert pepu.config.startswith('# %APPNAME% PEPU')


@pytest.mark.parametrize("channel_id", range(1, 7))
def test_read_in_channels(pepu, channel_id):
    pepu.conn._readline.return_value = '-1.2'
    channel = pepu.in_channels[channel_id]
    assert channel.value == -1.2


@pytest.mark.parametrize("channel_id", [7, 8])
def test_read_out_channels(pepu, channel_id):
    pepu.conn._readline.return_value = '-1'
    channel = pepu.out_channels[channel_id]
    value = channel.value
    pytest.xfail()
    assert value in (1.5, -1.5)


@pytest.mark.parametrize("channel_id", [1, 2])
def test_read_calc_channels(pepu, channel_id):
    pepu.conn._readline.return_value = '-1'
    channel = pepu.calc_channels[channel_id]
    value = channel.value
    pytest.xfail()
    assert value in (1.5, -1.5)


@pytest.mark.parametrize("acquisitions", [1, 2, 10])
@pytest.mark.parametrize("blocks", [1, 2, 10])
@pytest.mark.parametrize("block_size", [1, 2, 10])
def test_streams_acquisition(pepu, acquisitions, blocks, block_size):

    def mock_block(mock, n):
        mock._readline.return_value = '?*DSTREAM'
        header = b'\x01\x00\xa5\xa5'
        header += b'\x00\x00\x00\x00'
        header += b'\x00\x00\x00\x00'
        binary = b'\x80\x01\x00\x00\x00\x00\x00\x00'
        binary += b'\x80\xfe\xff\xff\xff\xff\x00\x00'
        values = [header, binary * n]
        mock._read.side_effect = lambda *args, **kwargs: values.pop(0)

    # Create stream
    stream = pepu.create_stream(
        name='TEST',
        trigger=Trigger(Signal.SOFT, Signal.SOFT),
        frequency=10, nb_points=blocks * block_size,
        sources=('CALC1', 'CALC2'),
        overwrite=True)

    # Mocking
    pepu.conn._readline.return_value = (
        'TEST OFF GLOBAL TRIG SOFT SOFT FSAMPL 10HZ NSAMPL {} SRC CALC1 CALC2'
        .format(blocks * block_size))

    # General testing
    assert stream.name == 'TEST'
    assert stream.trigger == Trigger(Signal.SOFT, Signal.SOFT)
    assert stream.frequency == 10
    assert stream.nb_points == blocks * block_size
    assert stream.sources == ['CALC1', 'CALC2']
    assert not stream.active

    # Loop over acquisitions
    for _ in range(acquisitions):
        pepu.conn._readline.return_value = ''
        stream.start()

        # Loop over blocks
        for _ in range(blocks):

            # Loop over points
            for _ in range(block_size):
                pepu.conn._readline.return_value = ''
                pepu.software_trigger()

            # Read nb points
            pepu.conn._readline.return_value = str(block_size)
            assert stream.nb_points_ready == block_size

            # Read data
            mock_block(pepu.conn, block_size)
            data = stream.read(n=block_size)

            # Test
            expected = [[1.5, -1.5]] * block_size
            assert data.tolist() == expected
