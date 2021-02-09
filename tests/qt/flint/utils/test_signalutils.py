"""Testing signalutils module."""


from bliss.flint.utils import signalutils


def test_trigger():
    obj = signalutils.InvalidatableSignal()
    a = []
    obj.triggered.connect(lambda: a.append(1))
    obj.trigger()
    assert a == [1]


def test_triggerIf():
    obj = signalutils.InvalidatableSignal()
    a = []
    obj.triggered.connect(lambda: a.append(1))
    obj.triggerIf(False)
    assert a == []
    obj.triggerIf(True)
    assert a == [1]


def test_validate():
    obj = signalutils.InvalidatableSignal()
    a = []
    obj.triggered.connect(lambda: a.append(1))
    assert a == []
    obj.invalidate()
    obj.validate()
    assert a == [1]


def test_triggerIf_validate():
    obj = signalutils.InvalidatableSignal()
    a = []
    obj.triggered.connect(lambda: a.append(1))
    obj.validate()
    obj.triggerIf(False)
    obj.triggerIf(False)
    obj.triggerIf(False)
    obj.triggerIf(False)
    assert a == []
    obj.validate()
    assert a == [1]
