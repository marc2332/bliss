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
    references = []

    # File containing the references
    mainfile = os.path.join(str(tmpdir), "main.h5")
    with nexus.nxRoot(mainfile, mode="w") as nxroot:
        nexus.nxEntry(nxroot, "entry0000")
        grp = nexus.nxEntry(nxroot, "entry0001")
        for i in range(5):
            name = str(len(references))
            grp[name] = i
            references.append(nexus.getUri(grp[name]))

    # External datasets to be references
    exfile = os.path.join(str(tmpdir), "ex.h5")
    with nexus.nxRoot(exfile, mode="w") as nxroot:
        for _ in range(5):
            grp = nexus.nxEntry(nxroot, str(len(references)))
            references.append(nexus.getUri(grp))

    # Add references
    nreferences = len(references)
    rproxy = ReferenceProxy(
        filename=mainfile, parent="/entry0000", nreferences=nreferences
    )
    rproxy.add_references(references[: nreferences // 2])
    rproxy.add_references(references[nreferences // 2 :])

    # Check result
    assert rproxy.npoints == nreferences
    assert rproxy.complete
    references2 = []
    with rproxy.open() as grp:
        for k in grp:
            if k.isdigit():
                references2.append(nexus.normUri(nexus.dereference(grp[k])))
    assert set(references) == set(references2)
