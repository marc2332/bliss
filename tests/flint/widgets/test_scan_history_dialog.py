"""Testing scatter plot."""

import pytest
import datetime

from bliss.flint.widgets import scan_history_dialog
from bliss.flint.helper import scan_history


@pytest.mark.usefixtures("local_flint")
def test_date_delegate():
    delegate = scan_history_dialog._DateDelegate()

    now = datetime.datetime.now()
    assert delegate.displayText(now, None) == "Today"

    now = datetime.datetime.now()
    yesterday = now - datetime.timedelta(days=1)
    assert delegate.displayText(yesterday, None) == "Yesterday"

    date = datetime.datetime(2000, 1, 1)
    assert delegate.displayText(date, None) == "2000-01-01"


def get_scans_description():
    scans = [
        scan_history.ScanDesc("foo1", datetime.datetime.now(), 2, "ct", "foo bar 1"),
        scan_history.ScanDesc("foo2", datetime.datetime.now(), 3, "ascan", "foo bar 2"),
        scan_history.ScanDesc("foo3", datetime.datetime.now(), 4, "foo", "foo bar 3"),
    ]
    return scans


@pytest.mark.usefixtures("local_flint")
def test_succeeded_dialog():
    dialog = scan_history_dialog.ScanHistoryDialog()
    scans = get_scans_description()
    dialog._loadingSucceeded.emit(scans)
    assert dialog._model().rowCount() == 2
    dialog.show()


@pytest.mark.usefixtures("local_flint")
def test_filter_dialog():
    dialog = scan_history_dialog.ScanHistoryDialog()
    dialog.setCategoryFilter(point=True, nscan=True, mesh=False, others=False)
    scans = get_scans_description()
    dialog._loadingSucceeded.emit(scans)
    assert dialog._model().rowCount() == 2
    dialog.setCategoryFilter(point=True, nscan=False, mesh=False, others=False)
    assert dialog._model().rowCount() == 1
    dialog.show()


@pytest.mark.usefixtures("local_flint")
def test_failed_dialog():
    dialog = scan_history_dialog.ScanHistoryDialog()
    try:
        raise RuntimeError("foo")
    except Exception as e:
        dialog._loadingFailed.emit(e)
    assert dialog._model().rowCount() == 0
    dialog.show()
