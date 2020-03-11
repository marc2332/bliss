from bliss.common.types import _scannable

import typeguard


def test_scannable_type(default_session):
    @typeguard.typechecked
    def func_with_scannable(axis: _scannable):
        return True

    bad = default_session.config.get("bad")
    bad.controller.bad_position = False

    assert func_with_scannable(bad) == True

    bad.controller.bad_position = True

    assert func_with_scannable(bad) == True
