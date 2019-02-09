import pytest
from bliss.controllers.mca.handel.error import HandelError, check_error


def test_no_error():
    assert check_error(0) is None


def test_known_error():
    with pytest.raises(HandelError) as context:
        check_error(801)
    assert str(context.value) == "[HandelError 801] UNIT_TEST"


def test_known_error_with_description():
    with pytest.raises(HandelError) as context:
        check_error(404)
    assert str(context.value) == "[HandelError 404] EOF: EOF encountered"


def test_unknown_error():
    with pytest.raises(HandelError) as context:
        check_error(802)
    assert str(context.value) == "[HandelError 802] UNKNOWN_ERROR_CODE"
