# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

SyncSrcList = ["Soft", "Int", "Ext"]

SyncTypeList = ["Gate", "StartStop", "TrigRdOut"]


def Rule1(*pars):
    start_src, trig_src, exp_src, exp_type = pars
    if exp_type in ["TrigRdOut"]:
        return trig_src == exp_src
    return True


def Rule2(*pars):
    start_src, trig_src, exp_src, exp_type = pars
    if exp_src == "Ext" and exp_type == "Gate":
        return start_src == "Ext" and trig_src == "Ext"
    return True


def Rule3(*pars):
    start_src, trig_src, exp_src, exp_type = pars
    if exp_src != "Ext" or exp_type != "StartStop":
        return True
    return (start_src == "Ext") == (trig_src == "Ext")


ModeRules = [("1", Rule1), ("2", Rule2), ("3", Rule3)]

ExistingModes = [
    ("IntTrigSingle", ("Soft", "Int", "Int", "Gate")),
    ("IntTrigMulti", ("Soft", "Soft", "Int", "Gate")),
    ("ExtTrigSingle", ("Ext", "Int", "Int", "Gate")),
    ("ExtTrigMulti", ("Ext", "Ext", "Int", "Gate")),
    ("ExtGate", ("Ext", "Ext", "Ext", "Gate")),
    ("ExtStartStop", ("Ext", "Ext", "Ext", "StartStop")),
    ("ExtTrigRdout", ("Soft", "Ext", "Ext", "TrigRdOut")),
]

NewModes = [
    ("IntTrigRdOut", ("Soft", "Int", "Int", "TrigRdOut")),
    ("SoftTrigRdOut", ("Soft", "Soft", "Soft", "TrigRdOut")),
]


def check_mode(*pars):
    return [name for name, rule in ModeRules if not rule(*pars)]


valid_modes = 0
trig, exp, rules = [], [], []
for exp_type in SyncTypeList:
    for exp_src in SyncSrcList:
        for trig_src in SyncSrcList:
            for start_src in SyncSrcList:
                pars = start_src, trig_src, exp_src, exp_type
                existing = [name for name, tpars in ExistingModes if pars == tpars]
                new = [name for name, tpars in NewModes if pars == tpars]
                invalid = check_mode(*pars)
                if not invalid:
                    valid_modes += 1

                trig.append("Trig=%s" % trig_src)
                exp.append("Exp=%s/%s" % (exp_src, exp_type))
                rule_str = ("** %s ** " % existing[0]) if existing else ""
                rule_str += ("++ %s ++ " % new[0]) if new else ""
                rule_str += (
                    ("-- INVALID (%s) --" % ",".join(invalid)) if invalid else ""
                )
                rules.append(rule_str)

ColWidth = 20
NbCols = 66
ColSep = " | "
RowSep = "-" * NbCols

l = [("%-*s" % (ColWidth, "Start=%s" % start_src)) for start_src in SyncSrcList]
print ColSep.join(l)
print RowSep


def group(x, n):
    return zip(*[x[i::n] for i in xrange(n)])


groups = map(lambda x: group(x, 3), (trig, exp, rules))

for t, e, r in zip(*groups):
    for l in t, e, r:
        print ColSep.join(["%-*s" % (ColWidth, s) for s in l])
    print RowSep

print "Valid Modes: %d" % valid_modes
print "Existing Modes: %d" % len(ExistingModes)
print "New Modes: %d" % len(NewModes)
