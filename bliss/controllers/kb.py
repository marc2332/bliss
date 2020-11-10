# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
class KbController: KB controller
class KbFocus: KB focusing procedures
"""

import tabulate
import click
import numpy as np

from bliss.controllers.motor import CalcController
from bliss.setup_globals import *
from bliss.common.scans import dscan
from bliss.config import settings
from bliss.common import plot
from bliss.shell.standard import umvr, umv
from bliss.common.utils import BOLD, YELLOW


def kb_plot(curve, y_data, x_data, x_cursor_pos=None, y_label="y", x_label="x"):
    """
    helper to plot ??? to put in flint ???
    """
    try:
        curve.clear_data()
    except:
        # FLINT 1.5 BUG: clear_data can't be called twice
        pass
    data = {x_label: x_data}
    if isinstance(y_data, list):
        for i in range(len(y_data)):
            data[y_label[i]] = y_data[i]
    else:
        data[y_label] = y_data
    if x_cursor_pos is not None:
        ymin, ymax = np.min(y_data), np.max(y_data)
        data["x_cursor"] = [x_cursor_pos, x_cursor_pos]
        data["y_cursor"] = [ymin, ymax]
    curve.add_data(data)
    if isinstance(y_data, list):
        for i in range(len(y_data)):
            curve.select_data(x_label, y_label[i])
    else:
        curve.select_data(x_label, y_label)
    if x_cursor_pos is not None:
        curve.select_data("x_cursor", "y_cursor", color="pink")


class KbController:
    """ KB mirror controller.
    """

    def __init__(self, name, config):

        self._name = name
        self._config = config
        self._setting = None

        # ???
        self._saving = config.get("saving", True)

        plot_list = {}
        self.__focus = {}
        focus_config = config.get("focus")

        # ???
        for focus in focus_config:
            kbfocus = focus.get("device")
            kbfocus.set_controller(self)
            self.__focus[kbfocus._name] = kbfocus
            setattr(self, kbfocus._name, kbfocus)
            plot_list[f"kb_focus_{kbfocus._name}"] = None

        self._setting_name = f"kb_{self._name}"
        self._setting = settings.HashSetting(
            self._setting_name, default_values=plot_list
        )

    def __info__(self):
        info_str = f"KB Controller {self._name}\n\n"
        for key in self.__focus:
            kbfocus = self.__focus[key]
            info_str += kbfocus.__info__() + "\n"
        return info_str

    # plot
    def _get_plot(self, title, plot_id):

        curve = None
        if self._setting is not None:
            if plot_id in self._setting:
                try:
                    flint_plot_id = self._setting[plot_id]
                    curve = plot.plot_curve(name=title, existing_id=flint_plot_id)
                except Exception as the_exception:
                    # In case flint was closed in between
                    print(the_exception)

            if curve is None:
                curve = plot.plot_curve(name=title)
            self._setting[plot_id] = curve._plot_id

        return curve


class KbFocus:
    """
    KbFocus is a class designed to focus a kb mirror.
    Two iteratives methods of focusing are provided, parabolic fitting
    and interaction matrix with 2 algorithms, one based on a parabolic
    fit and the other one on a linear regression.

    The principle is to change the bending of the mirror and to control
    the gain in term of focusing. The quality of focusing is depicted
    by a minimal movement of the beam (bpm counters) during a scan
    (rel_start rel_end) of slits.
    Once a correction has been done, we try to evaluate the next
    correction to apply considering the previous one and the gain.
    """

    def __init__(self, name, config):

        self._name = name
        self._config = config
        self._setting = None

        self._offs = config.get("offset_motor")
        self._offs_start = config.get("offset_start")
        self._bender_up = config.get("bender_upstream")
        self._bender_down = config.get("bender_downstream")
        self._bender_inc = config.get("bender_increment", 5)
        self._cnt = config.get("counter")

        self._corr_mode = "intm"

        self._stabt = 1  # stabilisation time (in s.)

    def __info__(self):
        info_str = f"KB Focus {self._name}\n"
        line1 = ["    ", "Slits Offset Motor", self._offs.name]
        line2 = ["    ", "Slits Offset Initial Pos.", self._offs_start]
        line3 = ["    ", "Upstream Bender Motor", self._bender_up.name]
        line4 = ["    ", "Downstream Bender Motor", self._bender_down.name]
        line5 = ["    ", "Counter", self._cnt.name]
        lines = [line1, line2, line3, line4, line5]
        info_str += tabulate.tabulate(lines, tablefmt="plain") + "\n"

        return info_str

    def set_controller(self, controller):
        """
        ???
        """
        self._controller = controller
        self._plot = controller._get_plot(
            f"KB Focus {self._name}", f"kb_focus_{self._name}"
        )

    def scan(self, start_position, end_position, nb_points, int_time):
        """
        Make a scan on slits and fits the data with a polynom of 2nd degree
        Args:
            (float): Start position
            (float): End position
            (int): Number of points
        Return:
            (Numpy Array, list): Scan data [
        """
        mot = self._offs
        cnt = self._cnt
        name = f"kbf_{self._name}"

        slit_scan = dscan(
            mot,
            start_position,
            end_position,
            nb_points,
            int_time,
            cnt,
            save=self._controller._saving,
            name=name,
        )
        slit_scan_data = slit_scan.get_data()

        #### Fit a polynom of 2nd order on the scan data
        coeffs = np.polyfit(slit_scan_data[mot.name], slit_scan_data[cnt.name], 2)

        data_mot = slit_scan_data[mot.name]
        data_raw = slit_scan_data[cnt.name]
        data_fit = np.copy(slit_scan_data[cnt.name])
        for idx in range(len(data_fit)):
            data_fit[idx] = (
                coeffs[0] * data_mot[idx] * data_mot[idx]
                + coeffs[1] * data_mot[idx]
                + coeffs[2]
            )

        return data_mot, data_raw, data_fit, coeffs

    def scan_plot(self):
        """
        ...
        """
        curve = self._controller._get_plot(
            f"KB Focus {self._name}", f"kb_focus_{self._name}"
        )
        kb_plot(
            curve,
            self._yplot_data,
            self._xplot_data,
            x_label=self._xplot_label,
            y_label=self._yplot_label,
        )

    def scan_print(self, data_raw, data_fit):
        # Display and save statistics about 1st scan:
        #   min/max/pic_to_valley/average/std_deviation on raw and fitted data.
        # Stats are saved to have an history of the changes.
        print(BOLD("\n    Scan statistics"))
        raw_min = np.min(data_raw)
        raw_max = np.max(data_raw)
        raw_ptv = raw_max - raw_min
        raw_std = np.std(data_raw)
        raw_avg = np.average(data_raw)
        fit_min = np.min(data_fit)
        fit_max = np.max(data_fit)
        fit_ptv = fit_max - fit_min
        fit_std = np.std(data_fit)
        fit_avg = np.average(data_fit)

        title_str = ["    ", "", "RAW", "FITTED"]
        min_str = ["    ", "MIN", f"{raw_min:.3f}", f"{fit_min:.3f}"]
        max_str = ["    ", "MAX", f"{raw_max:.3f}", f"{fit_max:.3f}"]
        ptv_str = ["    ", "PTV", f"{raw_ptv:.3f}", f"{fit_ptv:.3f}"]
        std_str = ["    ", "STD", f"{raw_std:.3f}", f"{fit_std:.3f}"]
        avg_str = ["    ", "AVG", f"{raw_avg:.3f}", f"{fit_avg:.3f}"]
        lines = [min_str, max_str, ptv_str, std_str, avg_str]
        mystr = tabulate.tabulate(lines, headers=title_str, tablefmt="plain")
        print(mystr)

    def _intm_quad_matrix(self):
        """
        Calculate Interaction Matrix - Quadratic Method
        """
        self.k = dict()
        self.k["a1"] = (self._coeff[1][0] - self._coeff[0][0]) / self._bender_inc
        self.k["a2"] = (self._coeff[2][0] - self._coeff[1][0]) / self._bender_inc
        self.k["b1"] = (self._coeff[1][1] - self._coeff[0][1]) / self._bender_inc
        self.k["b2"] = (self._coeff[2][1] - self._coeff[1][1]) / self._bender_inc

        self.det = self.k["a1"] * self.k["b2"] - self.k["b1"] * self.k["a2"]

        if self.det == 0:
            raise RuntimeError("Determinant == 0")
        if self.k["a1"] * self.k["a2"] * self.k["b1"] * self.k["b2"] == 0:
            raise RuntimeError("error: there is a 0 element in K")

    def _intm_quad_correction(self):
        """
        Calculate correction - Interaction Matrix - Quadratic Method
        """
        corr1 = (
            -self._coeff[-1][0] * self.k["b2"] + self._coeff[-1][1] * self.k["a2"]
        ) / self.det
        corr2 = (
            -self._coeff[-1][1] * self.k["a1"] + self._coeff[-1][0] * self.k["b1"]
        ) / self.det
        return (corr1, corr2)

    def _intm_linreg_matrix(self):
        """
        Calculate Interaction Matrix - Linear Regression Method

        https://fr.wikipedia.org/wiki/R%C3%A9gression_lin%C3%A9aire_multiple#Estimateur_des_moindres_carr.C3.A9s_ordinaires_.28EMCO.29
        given the interaction matrix H such as :
        y = H x C    (equation E1)
            y : m x 1 measured errors matrix  (m is number of points in the scans)
            H : m x 2 interaction matrix
            C : 2 x 1 matrix

         '' ( Ht . H )-1 . Ht . y '' is the solution to the minimization of errors y in equation E1 or something like that...
         Where Ht is the transpose matrix of H.
        """

        self._intm_dat_1 = (self._rawd[1] - self._rawd[0]) / self._bender_inc
        self._intm_dat_1 -= np.mean(self._intm_dat_1)

        self._intm_dat_2 = (self._rawd[2] - self._rawd[1]) / self._bender_inc
        self._intm_dat_2 -= np.mean(self._intm_dat_2)

        H = np.column_stack((self._intm_dat_1, self._intm_dat_2))

        tmp_I = np.linalg.inv(np.dot(H.transpose(), H))

        self._intm_matrix = np.dot(tmp_I, H.transpose())

    def _intm_linreg_correction(self):
        self._C = np.dot(self._intm_matrix, self._rawd[-1])
        corr1 = -self._C[0]
        corr2 = -self._C[1]
        return (corr1, corr2)

    def focus(self, start, stop, nbp, intt, bender_increment):
        self._coeff = []
        self._motd = []
        self._rawd = []
        self._fitd = []
        self._bender_inc = bender_increment

        self._partial = 100.0

        self._yplot_data = []
        self._yplot_label = []

        print(YELLOW("\nMoving Slit Offset Motor to intial position"))
        umv(self._offs, self._offs_start)

        print(YELLOW("\nGet intial beam profile"))
        # Scan 1
        (motd, rawd, fitd, coeff) = self.scan(start, stop, nbp, intt)
        self._xplot_data = motd
        self._xplot_label = f"{self._offs.name}"
        self._yplot_data.append(rawd)
        self._yplot_label.append(f"{self._cnt.name}_raw_1")
        self._yplot_data.append(fitd)
        self._yplot_label.append(f"{self._cnt.name}_fit_1")
        self.scan_plot()
        self.scan_print(rawd, fitd)

        self._coeff.append(coeff)
        self._motd.append(motd)
        self._rawd.append(rawd)
        self._fitd.append(fitd)

        print(YELLOW("\nMove Upstream Bender Motor and get beam profile"))
        # Move upstream bender
        umvr(self._bender_up, self._bender_inc)

        # Scan 2
        (motd, rawd, fitd, coeff) = self.scan(start, stop, nbp, intt)
        self._yplot_data.append(rawd)
        self._yplot_label.append(f"{self._cnt.name}_raw_2")
        self._yplot_data.append(fitd)
        self._yplot_label.append(f"{self._cnt.name}_fit_2")
        self.scan_plot()
        self.scan_print(rawd, fitd)

        self._coeff.append(coeff)
        self._motd.append(motd)
        self._rawd.append(rawd)
        self._fitd.append(fitd)

        print(YELLOW("\nMove Downstream Bender Motor and get beam profile"))
        # Move Downstream bender
        umvr(self._bender_down, self._bender_inc)

        # Scan 3
        (motd, rawd, fitd, coeff) = self.scan(start, stop, nbp, intt)
        self._yplot_data.append(rawd)
        self._yplot_label.append(f"{self._cnt.name}_raw_3")
        self._yplot_data.append(fitd)
        self._yplot_label.append(f"{self._cnt.name}_fit_3")
        self.scan_plot()
        self.scan_print(rawd, fitd)

        self._coeff.append(coeff)
        self._motd.append(motd)
        self._rawd.append(rawd)
        self._fitd.append(fitd)

        # Calculate Interaction Matrix - Linear Regression Method
        self._intm_linreg_matrix()

        # Calculate Interaction Matrix - Quadratic Method
        self._intm_quad_matrix()

        (corr1_quad, corr2_quad) = self._intm_quad_correction()
        (corr1_linreg, corr2_linreg) = self._intm_linreg_correction()

        self._nscan = 3
        end = False
        while not end:

            print(YELLOW("\nCorrections"))
            print("\n(a) Apply Interaction Matrix (Quadratic) and check Beam Profile")
            print(f"    {self._bender_up.name}: {corr1_quad:.3f}")
            print(f"    {self._bender_down.name}: {corr2_quad:.3f}")
            print(
                "(b) Apply Interaction Matrix (Linear Regression) and check Beam Profile"
            )
            print(f"    {self._bender_up.name}: {corr1_linreg:.3f}")
            print(f"    {self._bender_down.name}: {corr2_linreg:.3f}")
            print("(c) Exit\n")
            rep = click.prompt(BOLD("Your choice (a/b/c)"), default="c")
            if rep in ["a", "b", "c"]:
                if rep == "c":
                    end = True
                else:
                    msg = BOLD(f"Apply {self._partial}% of correction (0-100)")
                    self._partial = int(click.prompt(msg, default=self._partial))
                    if self._partial < 0:
                        self._partial = 0
                    if self._partial > 100:
                        self._partial = 100

                    if rep == "a":
                        corr1 = corr1_quad * self._partial / 100.0
                        corr2 = corr2_quad * self._partial / 100.0
                    else:
                        corr1 = corr1_linreg * self._partial / 100.0
                        corr2 = corr2_linreg * self._partial / 100.0

                    print(YELLOW("\nApply Bender Motor Corrections"))
                    pos1 = self._bender_up.position + corr1
                    pos2 = self._bender_down.position + corr2
                    print(
                        f"    {self._bender_up.name} Correction: {corr1:.3f} - New Position: {pos1:.3f}"
                    )
                    print(
                        f"    {self._bender_down.name} Correction: {corr2:.3f} - New Position: {pos2:.3f}"
                    )
                    umvr(self._bender_up, corr1)
                    umvr(self._bender_down, corr2)

                    print(YELLOW("\nGet Beam Profile"))
                    (motd, rawd, fitd, coeff) = self.scan(start, stop, nbp, intt)
                    self._nscan = self._nscan + 1
                    self._yplot_data.append(rawd)
                    self._yplot_label.append(f"{self._cnt.name}_raw_{self._nscan}")
                    self._yplot_data.append(fitd)
                    self._yplot_label.append(f"{self._cnt.name}_fit_{self._nscan}")
                    self.scan_plot()
                    self.scan_print(rawd, fitd)

                    self._coeff.append(coeff)
                    self._motd.append(motd)
                    self._rawd.append(rawd)
                    self._fitd.append(fitd)

                    (corr1_quad, corr2_quad) = self._intm_quad_correction()
                    (corr1_linreg, corr2_linreg) = self._intm_linreg_correction()


class KbMirrorCalcMotor(CalcController):
    def __init__(self, *args, **kwargs):
        CalcController.__init__(self, *args, **kwargs)
        self.distance = self.config.get("distance", float)

    def calc_from_real(self, reals_dict):
        pseudos_dict = {}
        pseudos_dict["tilt"] = reals_dict["rot"] + reals_dict["ecrot"]
        pseudos_dict["height"] = -reals_dict["ecrot"] * self.distance / 1000.0
        return pseudos_dict

    def calc_to_real(self, pseudos_dict):
        reals_dict = {}
        reals_dict["rot"] = (
            pseudos_dict["tilt"] + pseudos_dict["height"] * 1000.0 / self.distance
        )
        reals_dict["ecrot"] = -pseudos_dict["height"] * 1000.0 / self.distance
        return reals_dict
