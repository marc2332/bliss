
import pytest
import numpy

from bliss.common import scans
from bliss.common import event
from bliss.controllers.ct2.client import create_and_configure_device
from bliss.controllers.ct2.device import AcqStatus, StatusSignal, DataSignal


@pytest.fixture
def ct2(mocker):
    # Create ct2
    m = mocker.patch("bliss.controllers.ct2.client.Client")
    ct2 = create_and_configure_device(
        {
            "name": "myct2",
            "address": "some_host",
            "channels": [
                {"counter name": "c1", "address": 1},
                {"counter name": "c2", "address": 2},
            ],
        }
    )

    def start_acq():
        event.send(ct2, StatusSignal, AcqStatus.Ready)
        event.send(ct2, DataSignal, [(x + x / 10.) for x in range(1, 10)])

    # Patch ct2
    del ct2.counter_groups
    ct2.start_acq.side_effect = start_acq
    yield ct2


def test_ct2_scan(session, ct2):
    s = scans.ct(0.1, ct2)
    data = s.get_data()
    assert data["c1"] == [1]
    assert data["c2"] == [2]
