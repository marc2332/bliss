channel_type = {
    0: "Off",
    1: "TC",
    2: "mV",
    3: "V",
    4: "mA",
    5: "RTD",
    6: "Digital",
    7: "Test",
    8: "Ohms",
    9: "Dual mV",
    10: "Dual mA ",
    11: "Dual TC",
}

channel_lintype = {
    0: "Type B",
    1: "Type C",
    2: "Type D",
    3: "Type E",
    4: "Type G2",
    5: "Type J",
    6: "Type K",
    7: "Type L",
    8: "Type N",
    9: "Type R",
    10: "Type S",
    11: "Type T",
    12: "Type U",
    13: "NiMoNiCo",
    14: "Platinel",
    15: "NiNiMo",
    16: "Pt20RhPt40Rh ",
    17: "User 1",
    18: "User 2",
    19: "User 3",
    20: "User 4",
    21: "Cu10",
    22: "Pt100",
    23: "Pt100A",
    24: "JPT100",
    25: "Ni100",
    26: "Ni120",
    27: "Cu53",
    28: "Linear",
    29: "Sqrt",
    30: "x 3/2",
    32: "x 5/2",
}

name2address = dict(
    [
        ("channel.1.main.pv", ((0x0100 * 2) + 0x8000, "f")),
        ("channel.1.main.pv2", ((0x0110 * 2) + 0x8000, "f")),
        ("channel.1.main.type", (0x1800, "channel_type")),
        ("channel.1.main.status", (0x0101, "h")),
        ("channel.1.main.status2", (0x0111, "h")),
        ("channel.1.main.lintype", (0x1806, "channel_lintype")),
        ("channel.2.main.pv", ((0x0104 * 2) + 0x8000, "f")),
        ("channel.2.main.pv2", ((0x0114 * 2) + 0x8000, "f")),
        ("channel.2.main.type", (0x1880, "channel_type")),
        ("channel.2.main.status", (0x0105, "h")),
        ("channel.2.main.status2", (0x0115, "h")),
        ("channel.2.main.lintype", (0x1886, "channel_lintype")),
        ("channel.3.main.pv", ((0x0108 * 2) + 0x8000, "f")),
        ("channel.3.main.pv2", ((0x0118 * 2) + 0x8000, "f")),
        ("channel.3.main.type", (0x1900, "channel_type")),
        ("channel.3.main.status", (0x0109, "h")),
        ("channel.3.main.status2", (0x0119, "h")),
        ("channel.3.main.lintype", (0x1906, "channel_lintype")),
        ("channel.4.main.pv", ((0x010c * 2) + 0x8000, "f")),
        ("channel.4.main.pv2", ((0x011c * 2) + 0x8000, "f")),
        ("channel.4.main.type", (0x1980, "channel_type")),
        ("channel.4.main.status", (0x010d, "h")),
        ("channel.4.main.status2", (0x011d, "h")),
        ("channel.4.main.lintype", (0x1986, "channel_lintype")),
        ("loop.1.main.pv", ((0x0200 * 2) + 0x8000, "f")),
        (
            "loop.1.main.targetsp",
            (((0x0202 * 2) + 0x8000, "f"), ((0x0202 * 2) + 0x8000, "f", None)),
        ),
        ("loop.1.main.workingsp", ((0x0203 * 2) + 0x8000, "f")),
        (
            "loop.1.op.ch1onoffhysteresis",
            (((0x1672 * 2) + 0x8000, "f"), (0x1672, "h", 1)),
        ),
        ("loop.1.main.automan", (0x0201, "h")),
        ("loop.1.op.ch1out", (((0x020b * 2) + 0x8000, "f"), (0x020b, "h", 1))),
        ("loop.1.op.ch1potbreak", (0x1679, "b")),
        ("loop.1.op.ch1potposition", (((0x1678 * 2) + 0x8000, "f"), (0x1678, "h", 0))),
        ("loop.1.op.ch1traveltime", (((0x1674 * 2) + 0x8000, "f"), (0x1674, "h", 1))),
        ("loop.1.op.ch2deadband", (((0x166f * 2) + 0x8000, "f"), (0x166f, "h", 1))),
        (
            "loop.1.op.ch2onoffhysteresis",
            (((0x1673 * 2) + 0x8000, "f"), (0x1673, "h", 1)),
        ),
        ("loop.1.op.ch2out", (((0x020c * 2) + 0x8000, "f"), (0x020c, "h", 1))),
        ("loop.1.op.ch2potbreak", (0x167b, "b")),
        ("loop.1.op.ch2potposition", (((0x167a * 2) + 0x8000, "f"), (0x167a, "h", 0))),
        ("loop.1.op.ch2traveltime", (((0x1675 * 2) + 0x8000, "f"), (0x1675, "h", 1))),
        ("loop.1.op.cooltype", (0x1683, "b")),
        ("loop.1.op.enablepowerfeedforward", (0x1681, "b")),
        ("loop.1.op.feedforwardgain", (((0x1685 * 2) + 0x8000, "f"), (0x1685, "h", 3))),
        (
            "loop.1.op.feedforwardoffset",
            (((0x1686 * 2) + 0x8000, "f"), (0x1686, "h", 0)),
        ),
        (
            "loop.1.op.feedforwardtrimlimit",
            (((0x1687 * 2) + 0x8000, "f"), (0x1687, "h", 0)),
        ),
        ("loop.1.op.feedforwardtype", (0x1684, "b")),
        ("loop.1.op.feedforwardval", (((0x1688 * 2) + 0x8000, "f"), (0x1688, "h", 1))),
        ("loop.1.op.ff_rem", (((0x168d * 2) + 0x8000, "f"), (0x168d, "h", 1))),
        ("loop.1.op.forcedop", (((0x168f * 2) + 0x8000, "f"), (0x168f, "h", 1))),
        ("loop.1.op.manstartup", (0x1690, "b")),
        ("loop.1.op.manualmode", (0x167f, "b")),
        ("loop.1.op.manualoutval", (((0x1680 * 2) + 0x8000, "f"), (0x1680, "h", 1))),
        ("loop.1.op.measuredpower", (((0x1682 * 2) + 0x8000, "f"), (0x1682, "h", 0))),
        ("loop.1.op.nudgelower", (0x1677, "b")),
        ("loop.1.op.nudgeraise", (0x1676, "b")),
        ("loop.1.op.outputhighlimit", (((0x166d * 2) + 0x8000, "f"), (0x166d, "h", 1))),
        ("loop.1.op.outputlowlimit", (((0x166e * 2) + 0x8000, "f"), (0x166e, "h", 1))),
        ("loop.1.op.potbreakmode", (0x167c, "b")),
        ("loop.1.op.rate", (((0x1670 * 2) + 0x8000, "f"), (0x1670, "h", 1))),
        ("loop.1.op.ratedisable", (0x1671, "b")),
        ("loop.1.op.remoph", (((0x168c * 2) + 0x8000, "f"), (0x168c, "h", 1))),
        ("loop.1.op.remopl", (((0x168b * 2) + 0x8000, "f"), (0x168b, "h", 1))),
        ("loop.1.op.safeoutval", (((0x167e * 2) + 0x8000, "f"), (0x167e, "h", 1))),
        ("loop.1.op.sbrkop", (((0x168e * 2) + 0x8000, "f"), (0x168e, "h", 1))),
        ("loop.1.op.sensorbreakmode", (0x167d, "b")),
        ("loop.1.op.trackenable", (0x168a, "b")),
        ("loop.1.op.trackoutval", (((0x1689 * 2) + 0x8000, "f"), (0x1689, "h", 0))),
        ("loop.1.pid.boundary12", ((0x1639 * 2) + 0x8000, "f")),
        ("loop.1.pid.boundary23", ((0x163a * 2) + 0x8000, "f")),
        ("loop.1.pid.cutbackhigh", ((0x163f * 2) + 0x8000, "f")),
        ("loop.1.pid.cutbackhigh2", ((0x1647 * 2) + 0x8000, "f")),
        ("loop.1.pid.cutbackhigh3", ((0x164f * 2) + 0x8000, "f")),
        ("loop.1.pid.cutbacklow", ((0x1640 * 2) + 0x8000, "f")),
        ("loop.1.pid.cutbacklow2", ((0x1648 * 2) + 0x8000, "f")),
        ("loop.1.pid.cutbacklow3", ((0x1650 * 2) + 0x8000, "f")),
        ("loop.1.pid.derivativetime", (0x163d, "h")),
        ("loop.1.pid.derivativetime2", (0x5701, "h")),
        ("loop.1.pid.derivativetime3", (0x164d, "h")),
        ("loop.1.pid.integraltime", (0x163c, "h")),
        ("loop.1.pid.integraltime2", (0x1644, "h")),
        ("loop.1.pid.integraltime3", (0x164c, "h")),
        ("loop.1.pid.loopbreaktime", ((0x1642 * 2) + 0x8000, "f")),
        ("loop.1.pid.loopbreaktime2", ((0x164a * 2) + 0x8000, "f")),
        ("loop.1.pid.loopbreaktime3", ((0x1652 * 2) + 0x8000, "f")),
        ("loop.1.pid.manualreset", ((0x1641 * 2) + 0x8000, "f")),
        ("loop.1.pid.manualreset2", ((0x1649 * 2) + 0x8000, "f")),
        ("loop.1.pid.manualreset3", ((0x1651 * 2) + 0x8000, "f")),
        ("loop.1.pid.numsets", (0x1636, "b")),
        ("loop.1.pid.outputhi", ((0x1653 * 2) + 0x8000, "f")),
        ("loop.1.pid.outputhi2", ((0x1655 * 2) + 0x8000, "f")),
        ("loop.1.pid.outputhi3", ((0x1657 * 2) + 0x8000, "f")),
        ("loop.1.pid.outputlo", ((0x1654 * 2) + 0x8000, "f")),
        ("loop.1.pid.outputlo2", ((0x1656 * 2) + 0x8000, "f")),
        ("loop.1.pid.outputlo3", ((0x1658 * 2) + 0x8000, "f")),
        (
            "loop.1.pid.proportionalband",
            (((0x163b * 2) + 0x8000, "f"), (0x163b, "h", 1)),
        ),
        (
            "loop.1.pid.proportionalband2",
            (((0x1643 * 2) + 0x8000, "f"), (0x1643, "h", 1)),
        ),
        (
            "loop.1.pid.proportionalband3",
            (((0x164b * 2) + 0x8000, "f"), (0x164b, "h", 1)),
        ),
        ("loop.1.pid.relch2gain", ((0x163e * 2) + 0x8000, "f")),
        ("loop.1.pid.relch2gain2", ((0x1646 * 2) + 0x8000, "f")),
        ("loop.1.pid.relch2gain3", ((0x164e * 2) + 0x8000, "f")),
        ("loop.1.pid.schedulerremoteinput", ((0x1637 * 2) + 0x8000, "f")),
        ("loop.1.sp.altsp", ((0x1660 * 2) + 0x8000, "f")),
        ("loop.1.sp.altspselect", (0x1661, "b")),
        ("loop.1.sp.manualtrack", (0x1667, "b")),
        ("loop.1.sp.rangehigh", ((0x1659 * 2) + 0x8000, "f")),
        ("loop.1.sp.rangelow", ((0x165a * 2) + 0x8000, "f")),
        ("loop.1.sp.rate", ((0x1662 * 2) + 0x8000, "f")),
        ("loop.1.sp.ratedisable", (0x1663, "b")),
        ("loop.1.sp.ratedone", (0x020a, "b")),
        ("loop.1.sp.servotopv", ((0x166c * 2) + 0x8000, "f")),
        ("loop.1.sp.sp1", ((0x165c * 2) + 0x8000, "f")),
        ("loop.1.sp.sp2", ((0x165d * 2) + 0x8000, "f")),
        ("loop.1.sp.sphighlimit", ((0x165e * 2) + 0x8000, "f")),
        ("loop.1.sp.spintbal", ((0x166b * 2) + 0x8000, "f")),
        ("loop.1.sp.splowlimit", ((0x165f * 2) + 0x8000, "f")),
        ("loop.1.sp.spselect", ((0x165b * 2) + 0x8000, "f")),
        ("loop.1.sp.sptrack", ((0x1668 * 2) + 0x8000, "f")),
        ("loop.1.sp.sptrim", ((0x1664 * 2) + 0x8000, "f")),
        ("loop.1.sp.sptrimhighlimit", ((0x1665 * 2) + 0x8000, "f")),
        ("loop.1.sp.sptrimlowlimit", ((0x1666 * 2) + 0x8000, "f")),
        ("loop.1.sp.trackpv", ((0x1669 * 2) + 0x8000, "f")),
        ("loop.1.sp.tracksp", ((0x166a * 2) + 0x8000, "f")),
        ("loop.2.main.pv", ((0x0280 * 2) + 0x8000, "f")),
        (
            "loop.2.main.targetsp",
            (((0x0282 * 2) + 0x8000, "f"), ((0x0282 * 2) + 0x8000, "f", None)),
        ),
        ("loop.2.main.workingsp", ((0x0283 * 2) + 0x8000, "f")),
        (
            "loop.2.op.ch1onoffhysteresis",
            (((0x1772 * 2) + 0x8000, "f"), (0x1772, "h", 1)),
        ),
        ("loop.2.main.automan", (0x0281, "h")),
        ("loop.2.op.ch1out", (((0x028b * 2) + 0x8000, "f"), (0x028b, "h", 1))),
        ("loop.2.op.ch1potbreak", (0x1779, "b")),
        ("loop.2.op.ch1potposition", (((0x1778 * 2) + 0x8000, "f"), (0x1778, "h", 0))),
        ("loop.2.op.ch1traveltime", (((0x1774 * 2) + 0x8000, "f"), (0x1774, "h", 1))),
        ("loop.2.op.ch2deadband", (((0x176f * 2) + 0x8000, "f"), (0x176f, "h", 1))),
        (
            "loop.2.op.ch2onoffhysteresis",
            (((0x1773 * 2) + 0x8000, "f"), (0x1773, "h", 1)),
        ),
        ("loop.2.op.ch2out", (((0x028c * 2) + 0x8000, "f"), (0x028c, "h", 1))),
        ("loop.2.op.ch2potbreak", (0x177b, "b")),
        ("loop.2.op.ch2potposition", (((0x177a * 2) + 0x8000, "f"), (0x177a, "h", 0))),
        ("loop.2.op.ch2traveltime", (((0x1775 * 2) + 0x8000, "f"), (0x1775, "h", 1))),
        ("loop.2.op.cooltype", (0x1783, "b")),
        ("loop.2.op.enablepowerfeedforward", (0x1781, "b")),
        ("loop.2.op.feedforwardgain", (((0x1785 * 2) + 0x8000, "f"), (0x1785, "h", 3))),
        (
            "loop.2.op.feedforwardoffset",
            (((0x1786 * 2) + 0x8000, "f"), (0x1786, "h", 0)),
        ),
        (
            "loop.2.op.feedforwardtrimlimit",
            (((0x1787 * 2) + 0x8000, "f"), (0x1787, "h", 0)),
        ),
        ("loop.2.op.feedforwardtype", (0x1784, "b")),
        ("loop.2.op.feedforwardval", (((0x1788 * 2) + 0x8000, "f"), (0x1788, "h", 1))),
        ("loop.2.op.ff_rem", (((0x178d * 2) + 0x8000, "f"), (0x178d, "h", 1))),
        ("loop.2.op.forcedop", (((0x178f * 2) + 0x8000, "f"), (0x178f, "h", 1))),
        ("loop.2.op.manstartup", (0x1790, "b")),
        ("loop.2.op.manualmode", (0x177f, "b")),
        ("loop.2.op.manualoutval", (((0x1780 * 2) + 0x8000, "f"), (0x1780, "h", 1))),
        ("loop.2.op.measuredpower", (((0x1782 * 2) + 0x8000, "f"), (0x1782, "h", 0))),
        ("loop.2.op.nudgelower", (0x1777, "b")),
        ("loop.2.op.nudgeraise", (0x1776, "b")),
        ("loop.2.op.outputhighlimit", (((0x176d * 2) + 0x8000, "f"), (0x176d, "h", 1))),
        ("loop.2.op.outputlowlimit", (((0x176e * 2) + 0x8000, "f"), (0x176e, "h", 1))),
        ("loop.2.op.potbreakmode", (0x177c, "b")),
        ("loop.2.op.rate", (((0x1770 * 2) + 0x8000, "f"), (0x1770, "h", 1))),
        ("loop.2.op.ratedisable", (0x1771, "b")),
        ("loop.2.op.remoph", (((0x178c * 2) + 0x8000, "f"), (0x178c, "h", 1))),
        ("loop.2.op.remopl", (((0x178b * 2) + 0x8000, "f"), (0x178b, "h", 1))),
        ("loop.2.op.safeoutval", (((0x177e * 2) + 0x8000, "f"), (0x177e, "h", 1))),
        ("loop.2.op.sbrkop", (((0x178e * 2) + 0x8000, "f"), (0x178e, "h", 1))),
        ("loop.2.op.sensorbreakmode", (0x177d, "b")),
        ("loop.2.op.trackenable", (0x178a, "b")),
        ("loop.2.op.trackoutval", (((0x1789 * 2) + 0x8000, "f"), (0x1789, "h", 0))),
        ("loop.2.pid.boundary1-2", ((0x1739 * 2) + 0x8000, "f")),
        ("loop.2.pid.boundary2-3", ((0x173a * 2) + 0x8000, "f")),
        ("loop.2.pid.cutbackhigh", ((0x173f * 2) + 0x8000, "f")),
        ("loop.2.pid.cutbackhigh2", ((0x1747 * 2) + 0x8000, "f")),
        ("loop.2.pid.cutbackhigh3", ((0x174f * 2) + 0x8000, "f")),
        ("loop.2.pid.cutbacklow", ((0x1740 * 2) + 0x8000, "f")),
        ("loop.2.pid.cutbacklow2", ((0x1748 * 2) + 0x8000, "f")),
        ("loop.2.pid.cutbacklow3", ((0x1750 * 2) + 0x8000, "f")),
        ("loop.2.pid.derivativetime", (0x173d, "h")),
        ("loop.2.pid.derivativetime2", (0x1745, "h")),
        ("loop.2.pid.derivativetime3", (0x174d, "h")),
        ("loop.2.pid.integraltime", (0x173c, "h")),
        ("loop.2.pid.integraltime2", (0x1744, "h")),
        ("loop.2.pid.integraltime3", (0x174c, "h")),
        ("loop.2.pid.loopbreaktime", ((0x1742 * 2) + 0x8000, "f")),
        ("loop.2.pid.loopbreaktime2", ((0x174a * 2) + 0x8000, "f")),
        ("loop.2.pid.loopbreaktime3", ((0x1752 * 2) + 0x8000, "f")),
        ("loop.2.pid.manualreset", ((0x1741 * 2) + 0x8000, "f")),
        ("loop.2.pid.manualreset2", ((0x1749 * 2) + 0x8000, "f")),
        ("loop.2.pid.manualreset3", ((0x1751 * 2) + 0x8000, "f")),
        ("loop.2.pid.numsets", (0x1736, "b")),
        ("loop.2.pid.outputhi", ((0x1753 * 2) + 0x8000, "f")),
        ("loop.2.pid.outputhi2", ((0x1755 * 2) + 0x8000, "f")),
        ("loop.2.pid.outputhi3", ((0x1757 * 2) + 0x8000, "f")),
        ("loop.2.pid.outputlo", ((0x1754 * 2) + 0x8000, "f")),
        ("loop.2.pid.outputlo2", ((0x1756 * 2) + 0x8000, "f")),
        ("loop.2.pid.outputlo3", ((0x1758 * 2) + 0x8000, "f")),
        (
            "loop.2.pid.proportionalband",
            (((0x173b * 2) + 0x8000, "f"), (0x173b, "h", 1)),
        ),
        (
            "loop.2.pid.proportionalband2",
            (((0x1743 * 2) + 0x8000, "f"), (0x1743, "h", 1)),
        ),
        (
            "loop.2.pid.proportionalband3",
            (((0x174b * 2) + 0x8000, "f"), (0x174b, "h", 1)),
        ),
        ("loop.2.pid.relch2gain", ((0x173e * 2) + 0x8000, "f")),
        ("loop.2.pid.relch2gain2", ((0x1746 * 2) + 0x8000, "f")),
        ("loop.2.pid.relch2gain3", ((0x174e * 2) + 0x8000, "f")),
        ("loop.2.sp.altsp", ((0x1760 * 2) + 0x8000, "f")),
        ("loop.2.sp.altspselect", (0x1761, "b")),
        ("loop.2.sp.manualtrack", (0x1767, "b")),
        ("loop.2.sp.rangehigh", ((0x1759 * 2) + 0x8000, "f")),
        ("loop.2.sp.rangelow", ((0x175a * 2) + 0x8000, "f")),
        ("loop.2.sp.rate", ((0x1762 * 2) + 0x8000, "f")),
        ("loop.2.sp.ratedisable", ((0x1763 * 2) + 0x8000, "f")),
        ("loop.2.sp.ratedone", ((0x028a * 2) + 0x8000, "f")),
        ("loop.2.sp.servotopv", ((0x176c * 2) + 0x8000, "f")),
        ("loop.2.sp.sp1", ((0x175c * 2) + 0x8000, "f")),
        ("loop.2.sp.sp2", ((0x175d * 2) + 0x8000, "f")),
        ("loop.2.sp.sphighlimit", ((0x175e * 2) + 0x8000, "f")),
        ("loop.2.sp.spintbal", ((0x176b * 2) + 0x8000, "f")),
        ("loop.2.sp.splowlimit", ((0x175f * 2) + 0x8000, "f")),
        ("loop.2.sp.spselect", ((0x175b * 2) + 0x8000, "f")),
        ("loop.2.sp.sptrack", ((0x1768 * 2) + 0x8000, "f")),
        ("loop.2.sp.sptrim", ((0x1764 * 2) + 0x8000, "f")),
        ("loop.2.sp.sptrimhighlimit", ((0x1765 * 2) + 0x8000, "f")),
        ("loop.2.sp.sptrimlowlimit", ((0x1766 * 2) + 0x8000, "f")),
        ("loop.2.sp.trackpv", ((0x1769 * 2) + 0x8000, "f")),
        ("loop.2.sp.tracksp", ((0x176a * 2) + 0x8000, "f")),
    ]
)
