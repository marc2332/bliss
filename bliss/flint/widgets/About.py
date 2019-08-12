# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""About box for flint"""

__authors__ = ["V. Valls"]
__license__ = "MIT"
__date__ = "05/07/2018"

import os
import sys

from silx.gui import qt
from silx.gui import icons

import bliss.release


_LICENSE_TEMPLATE = """<p align="center">
<b>Copyright (C) 2015-{year} European Synchrotron Radiation Facility</b>
</p>

<p align="justify">
Distributed under the GNU LGPLv3. See LICENSE for more info.
</p>
"""


class About(qt.QDialog):
    """
    Util dialog to display an common about box for all the silx GUIs.
    """

    def __init__(self, parent=None):
        """
        :param files_: List of HDF5 or Spec files (pathes or
            :class:`silx.io.spech5.SpecH5` or :class:`h5py.File`
            instances)
        """
        super(About, self).__init__(parent)
        self.__createLayout()
        self.setSizePolicy(qt.QSizePolicy.Fixed, qt.QSizePolicy.Fixed)
        self.setModal(True)
        self.setApplicationName(None)

    def __createLayout(self):
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(24, 15, 24, 20)
        layout.setSpacing(8)

        self.__label = qt.QLabel(self)
        self.__label.setWordWrap(True)
        flags = self.__label.textInteractionFlags()
        flags = flags | qt.Qt.TextSelectableByKeyboard
        flags = flags | qt.Qt.TextSelectableByMouse
        self.__label.setTextInteractionFlags(flags)
        self.__label.setOpenExternalLinks(True)
        self.__label.setSizePolicy(qt.QSizePolicy.Minimum, qt.QSizePolicy.Preferred)

        licenseButton = qt.QPushButton(self)
        licenseButton.setText("License...")
        licenseButton.clicked.connect(self.__displayLicense)
        licenseButton.setAutoDefault(False)

        self.__options = qt.QDialogButtonBox()
        self.__options.addButton(licenseButton, qt.QDialogButtonBox.ActionRole)
        okButton = self.__options.addButton(qt.QDialogButtonBox.Ok)
        okButton.setDefault(True)
        okButton.clicked.connect(self.accept)

        layout.addWidget(self.__label)
        layout.addWidget(self.__options)
        layout.setStretch(0, 100)
        layout.setStretch(1, 0)

    def getHtmlLicense(self):
        """Returns the text license in HTML format.

        :rtype: str
        """
        from silx._version import __date__ as date

        year = date.split("/")[2]
        info = dict(year=year)
        textLicense = _LICENSE_TEMPLATE.format(**info)
        return textLicense

    def __displayLicense(self):
        """Displays the license used by silx."""
        text = self.getHtmlLicense()
        licenseDialog = qt.QMessageBox(self)
        licenseDialog.setWindowTitle("License")
        licenseDialog.setText(text)
        licenseDialog.exec_()

    def setApplicationName(self, name):
        self.__applicationName = name
        if name is None:
            self.setWindowTitle("About")
        else:
            self.setWindowTitle("About %s" % name)
        self.__updateText()

    def __updateText(self):
        """Update the content of the dialog according to the settings."""
        import silx._version

        message = """<table>
        <tr><td width="50%" align="center" valign="middle">
            <img src="{silx_image_path}" width="100" />
        </td><td width="50%" align="center" valign="middle">
            <b>{application_name}</b>
            <br />
            <br />{bliss_version}
            <br />
            <br /><a href="{project_url}">Upstream project at ESRF's GITLAB.</a>
        </td></tr>
        </table>
        <dl>
            <dt><b>Silx version</b></dt><dd>{silx_version}</dd>
            <dt><b>Qt version</b></dt><dd>{qt_version}</dd>
            <dt><b>Qt binding</b></dt><dd>{qt_binding}</dd>
            <dt><b>Python version</b></dt><dd>{python_version}</dd>
        </dl>
        <p>
        Copyright (C) <a href="{esrf_url}">European Synchrotron Radiation Facility</a>
        </p>
        """

        # Access to the logo in SVG or PNG
        logo = icons.getQFile("flint:" + os.path.join("logo", "flint-about"))

        info = dict(
            application_name=self.__applicationName,
            esrf_url="http://www.esrf.eu",
            project_url="https://gitlab.esrf.fr/bliss/bliss",
            silx_version=silx._version.version,
            bliss_version=bliss.release.short_version,
            qt_binding=qt.BINDING,
            qt_version=qt.qVersion(),
            python_version=sys.version.replace("\n", "<br />"),
            silx_image_path=logo.fileName(),
        )

        self.__label.setText(message.format(**info))
        self.__updateSize()

    def __updateSize(self):
        """Force the size to a QMessageBox like size."""
        screenSize = (
            qt.QApplication.desktop().availableGeometry(qt.QCursor.pos()).size()
        )
        hardLimit = min(screenSize.width() - 480, 1000)
        if screenSize.width() <= 1024:
            hardLimit = screenSize.width()
        softLimit = min(screenSize.width() / 2, 420)

        layoutMinimumSize = self.layout().totalMinimumSize()
        width = layoutMinimumSize.width()
        if width > softLimit:
            width = softLimit
            if width > hardLimit:
                width = hardLimit

        height = layoutMinimumSize.height()
        self.setFixedSize(width, height)

    @staticmethod
    def about(parent, applicationName):
        """Displays a silx about box with title and text text.

        :param qt.QWidget parent: The parent widget
        :param str title: The title of the dialog
        :param str applicationName: The content of the dialog
        """
        dialog = About(parent)
        dialog.setApplicationName(applicationName)
        dialog.exec_()
