# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
from nexus_writer_service.subscribers.reference_proxy import ReferenceProxy
from nexus_writer_service.io import nexus


def test_dataset_proxy(tmpdir):
    mainfile = str(tmpdir.join("main.h5"))
    exfile = str(tmpdir.join("ex.h5"))
    with nexus.nxRoot(mainfile, mode="w") as nxroot:
        nexus.nxEntry(nxroot, "destination")
        nexus.nxEntry(nxroot, "references")
    with nexus.nxRoot(exfile, mode="w") as nxroot:
        nexus.nxEntry(nxroot, "references")
    refmain = [f"{mainfile}::/references/{i}" for i in range(0, 5)]
    refex = [f"{exfile}::/references/{i}" for i in range(5, 10)]
    references = refmain + refex
    nreferences = len(references)

    # Add references (no self-referencing)
    rproxy = ReferenceProxy(
        filename=mainfile, parent="/destination", nreferences=nreferences
    )
    rproxy.add_references(references[: nreferences // 2])
    rproxy.add_references(references[nreferences // 2 :])
    assert rproxy.npoints == nreferences
    assert rproxy.complete
    with rproxy.open() as parent:
        references2 = [
            nexus.dereference(parent, name)
            for name in parent
            if nexus.isLink(parent, name)
        ]
    assert set(references) == set(references2)

    # Add references (self-referencing)
    rproxy = ReferenceProxy(
        filename=mainfile, parent="/references", nreferences=nreferences
    )
    rproxy.add_references(references[: nreferences // 2])
    rproxy.add_references(references[nreferences // 2 :])
    assert rproxy.npoints == nreferences
    assert rproxy.complete
    with rproxy.open() as parent:
        references2 = [
            nexus.dereference(parent, name)
            for name in parent
            if nexus.isLink(parent, name)
        ]
    assert set(refex) == set(references2)
