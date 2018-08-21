from mock import MagicMock
from bliss.scanning.scan import Scan


def test_scan_object(beacon):
    m = MagicMock()
    s = Scan(m, name="bla", run_number=3, writer=None)
    assert s.name == "bla_3"
    assert s.run_number == 3
    assert s.path is None
    assert str(s) == repr(s) == "Scan(name=bla_3, run_number=3)"

    m2 = MagicMock()
    m2.root_path = "/some/path"
    s = Scan(m, name="blu", run_number=4, writer=m2)
    assert s.name == "blu_4"
    assert s.run_number == 4
    assert s.path == "/some/path"
    assert str(s) == repr(s) == "Scan(name=blu_4, run_number=4, path=/some/path)"
