import pytest
from bliss.common import scans


def test_temperature_ct(session, temp_tin, temp_tout):
    scan = scans.ct(0.1, temp_tin, temp_tout, return_scan=True)
    data = scan.get_data()
    assert data[temp_tin.name][0] == pytest.approx(temp_tin.read())
    assert data[temp_tout.name][0] == pytest.approx(temp_tout.read())
