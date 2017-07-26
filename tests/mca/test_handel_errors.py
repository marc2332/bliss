import pytest
from bliss.controllers.mca.handel.error import HandelError, check_return_value


@check_return_value
def f(x):
    return x


def test_no_error():
    assert f(0) is None


def test_known_error():
    with pytest.raises(HandelError) as context:
        f(801)
    assert str(context.value) == "[HandelError 801] UNIT_TEST"


def test_known_error_with_description():
    with pytest.raises(HandelError) as context:
        f(404)
    assert str(context.value) == "[HandelError 404] EOF: EOF encountered"


def test_unknown_error():
    with pytest.raises(HandelError) as context:
        f(802)
    assert str(context.value) == "[HandelError 802] UNKNOWN_ERROR_CODE"
