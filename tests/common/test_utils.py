from collections import OrderedDict
import copy

import numpy
from ruamel.yaml import YAML
from ruamel.yaml.compat import StringIO

from bliss.common.utils import (
    flatten,
    merge,
    ShellStr,
    prudent_update,
    grouped_with_tail,
)


def test_flatten():
    assert flatten([1, 2, [3, 4, 5]]) == [1, 2, 3, 4, 5]
    assert flatten([1, 2, [3, 4, numpy.array((4, 5, 6))]]) == [1, 2, 3, 4, 4, 5, 6]
    assert flatten([1]) == [1]
    assert flatten([1, 3, 6]) == [1, 3, 6]


def test_merge():
    assert merge([[1, 2], [3]]) == [1, 2, 3]
    assert merge([[1, 2], [[3, 4]], [5]]) == [1, 2, [3, 4], 5]


def test_shell_str():
    raw_s = "<hi>"
    s = ShellStr(raw_s)
    assert s.__info__() == raw_s


def test_prudent_update_raw_0():
    d = {"a": {"b": [1, 2, 3]}}
    e = {"a": {"b": [2, 2, 3, 4]}}
    d = prudent_update(d, e)
    assert len(d["a"]["b"]) == 4
    assert d["a"]["b"][0] == 2
    assert d["a"]["b"][3] == 4


def test_prudent_update_raw_1():
    d = {"a": {"b": [1, 5, 3]}}
    e = {"a": {"b": [4, 5]}}
    d = prudent_update(e, d)
    assert d["a"]["b"] == [1, 5, 3]


def test_prudent_update_1():

    text = """name: rw_test
test: this is just a test.
# comment1
one: # comment2
- pink: martini  # comment3
  red: apples  # comment4
  blue: berry # comment5
two: # comment6
- a: true # comment7
  # comment8
  b: false # comment9
  c: null # comment10
    """
    yaml = YAML()
    raw = yaml.load(text)

    raw_updated = copy.deepcopy(raw)
    raw_updated["one"][0]["pink"] = "whisky"
    result = prudent_update(raw, raw_updated)

    stream = StringIO()
    yaml.dump(result, stream=stream)
    for comment in ("comment{}".format(i) for i in range(1, 11)):
        assert comment in stream.getvalue()

    raw_updated["one"] = ["first", "second"]
    result2 = prudent_update(raw, raw_updated)

    stream = StringIO()
    yaml.dump(result2, stream=stream)

    for comment in ("comment{}".format(i) for i in (1, 2, 7, 8, 9, 10)):
        assert comment in stream.getvalue()


test_dict = OrderedDict(
    {
        "device": [
            OrderedDict(
                {
                    "tango_name": "1/1/wagodummy",
                    "class": "Wago",
                    "properties": OrderedDict(
                        {
                            "Iphost": "localhost:36465",
                            "Protocol": "TCP",
                            "config": [
                                "750-504, foh2ctrl, foh2ctrl, foh2ctrl, foh2ctrl",
                                "750-408, foh2pos, sain2, foh2pos, sain4",
                                "750-408, foh2pos, sain6, foh2pos, sain8",
                                "750-408, pres",
                                "750-469, esTf1, esTf2",
                                "750-469, esTf3, esTf4",
                                "750-469, esTr1, esTr2",
                                "750-469, esTr3, esTr4",
                                "750-517, intlckf1, intlckf2",
                                "750-630, encoder1",
                                "750-508, special_out_1, special_out_2",
                                "750-554, o10v1, o10v2",
                                "750-517, double_out, double_out",
                            ],
                            "TCPTimeout": 1000,
                        }
                    ),
                }
            )
        ],
        "personal_name": "wago_tg_server",
        "server": "Wago",
    }
)

test_mut = {
    "device": [
        {
            "tango_name": "1/1/wagodummy",
            "class": "Wago",
            "properties": {
                "Iphost": "localhost:36465",
                "Protocol": "UDP",
                "config": [
                    "750-504, foh2ctrl, foh2ctrl, foh2ctrl, foh2ctrl",
                    "REPLACED",
                    "750-408, foh2pos, sain6, foh2pos, sain8",
                    "750-408, pres",
                    "750-469, esTf1, esTf2",
                    "750-469, esTf3, esTf4",
                    "750-469, esTr1, esTr2",
                    "750-469, esTr3, esTr4",
                    "750-517, intlckf1, intlckf2",
                    "750-630, encoder1",
                    "750-508, special_out_1, special_out_2",
                    "750-554, o10v1, o10v2",
                    "750-517, double_out, double_out",
                    "LAST",
                    {"hidden": 11},
                ],
                "TCPTimeout": 1000,
                "Another": 12,
            },
        }
    ],
    "personal_name": "wago_tg_server",
    "server": "Wago",
}


def test_prudent_update_2():
    out = prudent_update(test_dict, test_mut)
    assert isinstance(out, OrderedDict)
    assert out["device"][0]["properties"]["Protocol"] == "UDP"
    assert out["device"][0]["properties"]["config"][1] == "REPLACED"
    assert out["device"][0]["properties"]["config"][13] == "LAST"
    assert out["device"][0]["properties"]["Another"] == 12
    assert out["device"][0]["properties"]["config"][14]["hidden"] == 11


def test_grouped_with_tail():
    out = grouped_with_tail([1, 2, 3], 2)
    assert list(out) == [[1, 2], [3]]
    out = grouped_with_tail([1, 2, 3, 4], 2)
    assert list(out) == [[1, 2], [3, 4]]
    out = grouped_with_tail([1], 2)
    assert list(out) == [[1]]
    out = grouped_with_tail([], 2)
    assert list(out) == []
