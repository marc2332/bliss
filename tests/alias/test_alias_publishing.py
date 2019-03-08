
from bliss.common import scans


def test_alias_data_channel(alias_session):

    env_dict, session = alias_session

    s = scans.a2scan(
        env_dict["robyy"],
        0,
        5,
        env_dict["robzz"],
        0,
        5,
        5,
        0.001,
        env_dict["simu1"].counters.spectrum_det0,
        env_dict["dtime"],
        env_dict["lima_simulator"].roi_counters.r1.sum,
        env_dict["lima_simulator"].roi_counters.r2.sum,
        env_dict["myroi3"],
        save=True,
        return_scan=True,
    )

    dump1 = """test_alias:{a2scan}:axis:roby robyy
test_alias:{a2scan}:axis:robz robzz
test_alias:{a2scan}:axis:timer:elapsed_time None
test_alias:{a2scan}:axis:timer:lima_simulator:roi_counters:r1:sum myroi
test_alias:{a2scan}:axis:timer:lima_simulator:roi_counters:r2:sum None
test_alias:{a2scan}:axis:timer:lima_simulator:roi_counters:r3:sum myroi3
test_alias:{a2scan}:axis:timer:simu1:deadtime_det0 dtime
test_alias:{a2scan}:axis:timer:simu1:spectrum_det0 None""".format(
        a2scan=s.node.name
    ).split(
        "\n"
    )

    for n in s.node.iterator.walk(filter="channel", wait=False):
        assert " ".join([n.db_name, n.alias]) in dump1

    dump2 = """test_alias:{a2scan}:axis:roby True
test_alias:{a2scan}:axis:robz True
test_alias:{a2scan}:axis:timer:elapsed_time False
test_alias:{a2scan}:axis:timer:lima_simulator:roi_counters:r1:sum True
test_alias:{a2scan}:axis:timer:lima_simulator:roi_counters:r2:sum False
test_alias:{a2scan}:axis:timer:lima_simulator:roi_counters:r3:sum True
test_alias:{a2scan}:axis:timer:simu1:deadtime_det0 True
test_alias:{a2scan}:axis:timer:simu1:spectrum_det0 False""".format(
        a2scan=s.node.name
    ).split(
        "\n"
    )

    for n in s.node.iterator.walk(filter="channel", wait=False):
        assert " ".join([n.db_name, str(n.has_alias)]) in dump2
