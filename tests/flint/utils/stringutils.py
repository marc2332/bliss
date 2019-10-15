"""Testing stringutils module."""


from bliss.flint.utils import stringutils


def test_human_readable_duration():
    assert "2 seconds" in stringutils.human_readable_duration(seconds=2)
    assert "20 seconds" in stringutils.human_readable_duration(seconds=20)
    assert "3 minutes" in stringutils.human_readable_duration(seconds=200)
    assert "second" in stringutils.human_readable_duration(seconds=200)
    assert "33 minutes" in stringutils.human_readable_duration(seconds=2000)
    assert "second" not in stringutils.human_readable_duration(seconds=2000)
    assert "5 hours" in stringutils.human_readable_duration(seconds=20000)
    assert "second" not in stringutils.human_readable_duration(seconds=20000)


def test_human_readable_duration_in_second():
    assert "2 seconds" in stringutils.human_readable_duration_in_second(seconds=2)
    assert "20 seconds" in stringutils.human_readable_duration_in_second(seconds=20)
    assert "3 minutes" in stringutils.human_readable_duration_in_second(seconds=200)
    assert "33 minutes" in stringutils.human_readable_duration_in_second(seconds=2000)
    assert "5 hours" in stringutils.human_readable_duration_in_second(seconds=20000)
