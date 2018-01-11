# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""X-Ray crystal diffraction physics (Bragg, Laue)

Disclaimer
----------

The following module uses the SI system of units.
All arguments which represent physical quantities must be given
in the corresponding SI value. Failure to comply will result
in unexpected values for the user.

Theory
------

De Broglie
~~~~~~~~~~

:math:`{\\lambda} = h / p`

where:

* λ: wavelength
* h: Planck constant
* p: momentum


Bragg's law
~~~~~~~~~~~

:math:`n{\\lambda} = 2dsin({\\theta})`

**X-rays**

Since :math:`v = c`, :math:`E = mc^2` and :math:`p = mv` then
:math:`{\\lambda} = hc / E {\\Leftrightarrow} E = hc / {\\lambda}`

and:

:math:`E = nhc / 2dsin({\\theta})`

where:

* n: order of reflection [1..]
* λ: wavelength incident angle
* θ: scattering angle
* d: interplanar distance between lattice planes

**Cubic crystal diffraction**

:math:`d = a / {\\sqrt{h^2+k^2+l^2}}`

where:

* d: interplanar distance between lattice planes
* a: lattice spacing of the cubic crystal

Examples
--------

Bragg energy & angle
~~~~~~~~~~~~~~~~~~~~

How to find the bragg angle (in degrees) for a silicon crystal at the 110 plane
when the energy is 12.5 keV::

    >>> from numpy import rad2deg
    >>> from bliss.physics.diffraction import Si
    >>> Si110 = Si('110')
    >>> energy_keV = 12.5
    >>> energy_J = energy_keV  * 1.60218e-16
    >>> angle_rad = Si110.bragg_angle(energy_J)
    >>> angle_deg = rad2deg(angle_rad)

How to find the bragg energy (keV) for a germanium crystal at 444 plane when
the angle is 2.4 degrees::

    >>> from numpy import deg2rad
    >>> from bliss.physics.diffraction import Ge
    >>> Ge444 = Ge('444')
    >>> angle_deg = 2.4
    >>> angle_rad = deg2rad(angle_deg)
    >>> energy_J = Ge444.bragg_energy(angle_rad)
    >>> energy_keV = energy_J / 1.60218e-16

New crystal
~~~~~~~~~~~

The library provides *pure single element cubic crystal object*. If you need a
new exotic crystal with a specific lattice you can just create a new crystal
like this::

    SiGeMix = Crystal(('SiGe hybrid', 3.41e-10))

More complex crystals may require you to inherit from Crystal or create your own
object with the same interface as Crystal (ie. duck typing)
"""

from collections import namedtuple

from numpy import sqrt, sin, arcsin
from scipy.constants import h, c

hc = h * c


#: A crystal Plane in hkl coordinates
HKL = namedtuple('HKL', 'h k l')


def string_to_hkl(text):
    """
    Convert a string representing hkl plane to a HKL object.

    Args:
        text (str): string with three integers separated by single space
                    (ex: '1 1 0', '10 10 0'). If all planes are one digit
                    long, it also accepts a compact format without spaces
                    (ex: '111', '110').
    Returns:
        HKL: the crystal plane for the given hkl coordinates
    Raises:
        ValueError: if argument is not in the correct format
    """
    try:
        if len(text) == 3:
            return HKL(*map(int, text))
        elif ' ' in text:
            return HKL(*map(int, text.split()))
    except Exception as err:
        raise ValueError('Invalid crystal plane {0!r}: {1}'.format(text, err))
    raise ValueError('Invalid crystal plane {0!r}'.format(text))


def hkl_to_string(hkl):
    """Returns string representation of a HKL plane"""
    join = '' if all(map(lambda i: i<10, hkl)) else ' '
    return join.join(map(str, hkl))


HKL.fromstring = staticmethod(string_to_hkl)
HKL.tostring = hkl_to_string


def wavelength_to_energy(wavelength):
    """
    Returns photon energy (J) for the given wavelength (m)

    Args:
        wavelength (float): photon wavelength (m)
    Returns:
        float: photon energy (J)
    """
    return hc / wavelength


def energy_to_wavelength(energy):
    """
    Returns photon wavelength (m) for the given energy (J)

    Args:
        energy (float): photon energy (J)
    Returns:
        float: photon wavelength (m)
    """
    return hc / energy


def distance_lattice_diffraction_plane(h, k, l, a):
    """
    Calculates the interplanar distance between lattice planes for a specific
    diffraction plane (given by h, k, l) and a specific lattice with lattice
    parameter *a*: :math:`d = a / {\\sqrt{h^2+k^2+l^2}}`

    Args:
        h (float): a diffraction plane *h*
        k (float): a diffraction plane *k*
        l (float): a diffraction plane *l*
        a (float): crystal lattic parameter *a*
    Returns:
        float: the distance (d) between lattice planes
    """
    return a / sqrt(h**2 + k**2 + l**2)


def bragg_wavelength(theta, d, n=1):
    """
    Return a bragg wavelength (m) for the given theta and distance between
    lattice planes.

    Args:
        theta (float): scattering angle (rad)
        d (float): interplanar distance between lattice planes (m)
        n (int): order of reflection. Non zero positive integer (default: 1)
    Returns:
        float: bragg wavelength (m) for the given theta and lattice distance
    """
    return 2 * d * sin(theta) / n


def bragg_energy(theta, d, n=1):
    """
    Return a bragg energy for the given theta and distance between lattice
    planes.

    Args:
        theta (float): scattering angle (rad)
        d (float): interplanar distance between lattice planes (m)
        n (int): order of reflection. Non zero positive integer (default: 1)
    Returns:
        float: bragg energy (J) for the given theta and lattice distance
    """
    return wavelength_to_energy(bragg_wavelength(theta, d, n=n))


def bragg_angle(energy, d, n=1):
    """
    Return a bragg angle (rad) for the given theta and distance between
    lattice planes.

    Args:
        energy (float): energy (J)
        d (float): interplanar distance between lattice planes (m)
        n (int): order of reflection. Non zero positive integer (default: 1)
    Returns:
        float: bragg angle (rad) for the given theta and lattice distance
    """
    return arcsin( n * hc / (2 * d * energy))


def string_to_crystal_plane(text):
    """
    Return a crystal plane from a string. Accepts format:
    <symbol>['(']<plane>[')'].

    Examples::

        >>> from bliss.physics.diffraction import string_to_crystal_plane

        >>> Si110011 = string_to_crystal_plane('Si(11 00 11)')
        >>> Si110 = string_to_crystal_plane('Si110')

    Args:
        text (str): text representing a crystal plane
    Returns:
        CrystalPlane: the corresponding crystal plane object
    Raises:
        KeyError: if crystal is not registered
        ValueError: is plane is in wrong format
    """
    symbol, plane = '', ''
    for c in text:
        if c.isdigit() or c.isspace():
            plane += c
        elif c.isalpha():
            symbol += c
    return globals()[symbol](plane)


class CrystalPlane(object):
    """
    Cubic crystal plane.

    This object should not be created directly. Instead you should
    get it from the Crystal::

        >>> from bliss.physics.diffraction import Si

        >>> Si111 = Si('111')
        >>> e_at_50mrad = Si111.bragg_energy(50e-3)
    """

    def __init__(self, crystal, plane):
        self.crystal = crystal
        self.plane = plane
        # may optimize in the future
        (h, k, l), a = self.plane, self.crystal.lattice_constant
        self.d = distance_lattice_diffraction_plane(h, k, l, a)

    def bragg_wavelength(self, theta, n=1):
        """
        Returns a bragg wavelength (m) for the given theta on this crystal plane

        Args:
            theta (float): scattering angle (rad)
            n (int): order of reflection. Non zero positive integer (default: 1)
        Returns:
            float: bragg wavelength (m) for the given theta and lattice distance
        """
        return bragg_wavelength(theta, self.d, n=n)

    def bragg_energy(self, theta, n=1):
        """
        Returns a bragg energy (J) for the given theta on this crystal plane

        Args:
            theta (float): scattering angle (rad)
            n (int): order of reflection. Non zero positive integer (default: 1)
        Returns:
            float: bragg energy (J) for the given theta and lattice distance
        """
        return bragg_energy(theta, self.d, n=n)

    def bragg_angle(self, energy, n=1):
        """
        Returns a bragg angle (rad) for the given energy on this crystal plane

        Args:
            energy (float): energy (J)
            n (int): order of reflection. Non zero positive integer (default: 1)
        Returns:
            float: bragg angle (rad) for the given theta and lattice distance
        """
        return bragg_angle(energy, self.d, n=n)

    def __repr__(self):
        return '{0}({1})'.format(self.crystal, self.plane.tostring())

    @staticmethod
    def fromstring(text): 
        """
        Return a crystal plane from a string. Accepts format:
        <symbol>['(']<plane>[')'].

        Examples::

            >>> from bliss.physics.diffraction import CrystalPlane

            >>> Si110011 = CrystalPlane.fromstring('Si(11 00 11)')
            >>> Si110 = CrystalPlane.fromstring('Si110')

        Args:
            text (str): text representing a crystal plane
        Returns:
            CrystalPlane: the corresponding crystal plane object
        Raises:
            KeyError: if crystal is not registered
            ValueError: is plane is in wrong format
        """
        return string_to_crystal_plane(text)


class Crystal(object):
    """
    Cubic crystal.

    Example::

        >>> from bliss.physics.diffraction import Crystal
        >>> Si = Crystal()
        >>> Si111 = Si('111')

    Note that most crystals are already available at the module level
    so you rarely need to create an instance of this class::

        >>> bliss.physics.diffraction.Si
        Si
        >>> bliss.physics.diffraction.Ge
        Ge
    
    """

    def __init__(self, element):
        if isinstance(element, (list, tuple)):
            name, a = element
        else:
            name, a = element.symbol, element.lattice_constant * 1e-10
        self.name = name
        self.lattice_constant = a
        #: diffraction planes cache dict<hkl(str): planes(CrystalPlane)>
        self._planes = {}

    def __call__(self, plane):
        """Helper to get a crystal plane from a string (ex: '110')"""
        if isinstance(plane, CrystalPlane):
            self._planes[plane.tostring()] = plane
            return plane
        try:
            return self._planes[plane]
        except KeyError:
            pass
        result = CrystalPlane(self, HKL.fromstring(plane))
        self._planes[plane] = result
        return result

    def bragg_wavelength(self, theta, plane, n=1):
        """
        Returns a bragg wavelength (m) for the given theta on the given plane

        Args:
            theta (float): scattering angle (rad)
            plane (str or CrystalPlane): crystal plane
            n (int): order of reflection. Non zero positive integer (default: 1)
        Returns:
            float: bragg wavelength (m) for the given theta and lattice distance
        """
        return self(plane).bragg_wavelength(theta, n=n)

    def bragg_energy(self, theta, plane, n=1):
        """
        Returns a bragg energy (J) for the given theta on the given plane

        Args:
            theta (float): scattering angle (rad)
            plane (str or CrystalPlane): crystal plane
            n (int): order of reflection. Non zero positive integer (default: 1)
        Returns:
            float: bragg energy (J) for the given theta and lattice distance
        """
        return self(plane).bragg_energy(theta, n=n)

    def bragg_angle(self, energy, plane, n=1):
        """
        Returns a bragg angle (read) for the given energy on the given plane

        Args:
            energy (float): energy (J)
            plane (str or CrystalPlane): crystal plane
            n (int): order of reflection. Non zero positive integer (default: 1)
        Returns:
            float: bragg energy (J) for the given theta and lattice distance
        """
        return self(plane).bragg_angle(energy, n=n)

    def __repr__(self):
        return self.name


# export all periodic table element cubic crystals

import mendeleev.elements

def _get_all_crystals():
    result = []
    for elem_symbol in mendeleev.elements.__all__:
        elem = getattr(mendeleev.elements, elem_symbol)
        if elem.lattice_constant is not None:
            result.append(Crystal(elem))
    return result

globals().update({c.name: c for c in _get_all_crystals()})
