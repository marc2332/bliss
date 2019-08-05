# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy
import traceback
from bliss.common.msgpack_ext import MsgpackContext


def test_default():
    context = MsgpackContext()
    value = [1, 2, 5, b"string"]
    msg = context.packb(value, use_bin_type=True)

    unpacker = context.Unpacker(raw=True)
    unpacker.feed(msg)
    results = list(unpacker)
    assert len(results) == 1
    result = results[0]
    assert result == value


def test_numpy():
    context = MsgpackContext()
    context.register_numpy()

    value = numpy.array([1, 2, 3, 4, 5])
    msg = context.packb(value, use_bin_type=True)
    unpacker = context.Unpacker(raw=True)
    unpacker.feed(msg)
    results = list(unpacker)
    assert len(results) == 1
    result = results[0]
    assert isinstance(result, numpy.ndarray)
    assert list(result) == list(value)


class Foo(object):
    pass


def test_pickle():
    context = MsgpackContext()
    context.register_pickle()

    value = Foo()
    msg = context.packb(value, use_bin_type=True)
    unpacker = context.Unpacker(raw=True)
    unpacker.feed(msg)
    results = list(unpacker)
    assert len(results) == 1
    result = results[0]
    assert isinstance(result, Foo)


def test_pickle_exception():
    context = MsgpackContext()
    context.register_pickle()

    try:
        raise TypeError("Fooo")
    except Exception as e:
        value = e

    msg = context.packb(value, use_bin_type=True)
    unpacker = context.Unpacker(raw=True)
    unpacker.feed(msg)
    results = list(unpacker)
    assert len(results) == 1
    result = results[0]
    assert isinstance(result, TypeError)
    assert result.__traceback__ is None


def test_pickle_tb_exception():
    context = MsgpackContext()
    context.register_tb_exception()
    # Still can register pickle
    context.register_pickle()

    try:
        raise TypeError("Fooo")
    except Exception as e:
        value = e

    msg = context.packb(value, use_bin_type=True)
    unpacker = context.Unpacker(raw=True)
    unpacker.feed(msg)
    results = list(unpacker)
    assert len(results) == 1
    result = results[0]
    assert isinstance(result, TypeError)
    assert result.__traceback__ is not None
    tb = traceback.format_tb(result.__traceback__)
    assert "test_pickle_tb_exception" in tb[0]


class MyException(Exception):
    pass


def test_pickle_custom_exception():
    context = MsgpackContext()
    context.register_tb_exception()

    try:
        raise MyException("fooo", 10)
    except Exception as e:
        value = e

    msg = context.packb(value, use_bin_type=True)
    unpacker = context.Unpacker(raw=True)
    unpacker.feed(msg)
    results = list(unpacker)
    assert len(results) == 1
    result = results[0]
    assert isinstance(result, MyException)
    assert result.__traceback__ is not None
    tb = traceback.format_tb(result.__traceback__)
    assert "test_pickle_custom_exception" in tb[0]
