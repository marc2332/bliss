
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
        env_dict["lima_simulator"].counters.r1_sum,
        env_dict["lima_simulator"].counters.r2_sum,
        env_dict["myroi3"],
        save=True,
        return_scan=True,
    )

    dump1 = """{a2scan}:axis:robyy robyy
{a2scan}:axis:robzz robzz
{a2scan}:axis:timer:elapsed_time elapsed_time
{a2scan}:axis:timer:epoch epoch
{a2scan}:axis:timer:lima_simulator:roi_counters:myroi myroi
{a2scan}:axis:timer:lima_simulator:roi_counters:r2_sum r2_sum
{a2scan}:axis:timer:lima_simulator:roi_counters:myroi3 myroi3
{a2scan}:axis:timer:simu1:dtime dtime
{a2scan}:axis:timer:simu1:spectrum_det0 spectrum_det0""".format(
        a2scan=s.node.db_name
    ).split(
        "\n"
    )

    d = list()
    for n in s.node.iterator.walk(filter="channel", wait=False):
        assert " ".join([n.db_name, n.name]) in dump1
