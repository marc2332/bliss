# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""X-Ray crystal diffraction physics (Bragg, Laue)

Disclaimer
----------

When an argument to any function represents a physical quantity, the library
expects the units to be coherent. Passing Quantity objects makes sure you are
coherent.

The implementation is permissive, which means that if you pass a float/int
instead of a Quantity, the library assumes the argument to be in the correct
units which are SI units. Failure to comply will result in unexpected values.

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

    >>> from bliss.physics.units import ur
    >>> from bliss.physics.diffraction import Si
    >>> keV, deg = ur.keV, ur.deg

    >>> Si110 = Si('110')

    >>> energy = 12.5*keV
    >>> angle = Si110.bragg_angle(energy)

    # angle is a Quantity (radians)
    >>> print( angle )
    0.12952587191 radian

    # view it as a Quantity (degrees)
    >>> print( angle.to(deg) )
    7.42127016 degree

    # get the float in degrees
    >>> print( angle.to('deg').magnitude )
    7.42127016


... it also works for an arrays::

    >>> from numpy import array
    >>> energies = array([5.1, 12.5, 17.4])*keV
    >>> angles = Si110.bragg_angle(energies)

    # angles is a numpy array of Quantity (radians)
    >>> print( angles )
    [ 0.32212021  0.12952587  0.0929239 ] radian

    # view as numpy array of Quantity (degrees)
    >>> print( angles.to(deg) )
    [ 18.45612869   7.4212858    5.32414748] degree

    # get the underlying numpy of float64
    >>> print( angles.to(deg).magnitude )
    [ 18.45612869   7.4212858    5.32414748]


...if you want to handle units yourself (disadvised):

    >>> from numpy import rad2deg

    >>> Si110 = Si('110')
    >>> energy_keV = 12.5
    >>> energy_J = energy_keV  * 1.60218e-16
    >>> angle_rad = Si110.bragg_angle(energy_J)
    >>> angle_deg = rad2deg(angle_rad)
    >>> angle_deg
    7.42127016


How to find the bragg energy (keV) for a germanium crystal at 444 plane when
the angle is 25.6 degrees::

    >>> from bliss.physics.diffraction import Ge
    >>> deg = ur.deg

    >>> Ge444 = Ge('444')
    >>> angle = 25.6*deg
    >>> energy = Ge444.bragg_energy(angle)

    >>> print( energy.to(keV) )
    17.5618627264 kiloelectron_volt

    >>> print( energy.to(ur.keV).magnitude )
    17.5618627264

New crystal
~~~~~~~~~~~

The library provides *pure single element cubic crystal object*. If you need a
new exotic crystal with a specific lattice you can just create a new crystal
like this::

    SiGeMix = Crystal(('SiGe hybrid', 3.41e-10))

More complex crystals may require you to inherit from Crystal or create your
own object with the same interface as Crystal (ie. duck typing)

Multi-crystal plane
~~~~~~~~~~~~~~~~~~~

It is possible to define multi-crystal planes by providing the interplanar
distance::

    >>> from bliss.physics.diffraction import MultiPlane

    >>> my_plane = MultiPlane(distance=5.0e-10)
    >>> e = my_plane.bragg_energy(50e-3)
"""

from collections import namedtuple

from mendeleev import elements
from numpy import sqrt, sin, arcsin

from .units import ur, units

hc = (1 * (ur.h * ur.c)).to(ur.kg * ur.m ** 3 / ur.s ** 2)


#: A crystal Plane in hkl coordinates
HKL = namedtuple("HKL", "h k l")


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
        strings = list(text) if len(text) <= 3 else text.split()
        return HKL(*list(map(int, strings)))
    except Exception as err:
        raise ValueError("Invalid crystal plane {0!r}: {1}".format(text, err))


def hkl_to_string(hkl):
    """Returns string representation of a HKL plane"""
    join = "" if all([i < 10 for i in hkl]) else " "
    return join.join(map(str, hkl))


HKL.fromstring = staticmethod(string_to_hkl)
HKL.tostring = hkl_to_string


@units(wavelength="m", result="J")
def wavelength_to_energy(wavelength):
    """
    Returns photon energy (J) for the given wavelength (m)

    Args:
        wavelength (float): photon wavelength (m)
    Returns:
        float: photon energy (J)
    """
    return hc / wavelength


@units(energy="J", result="m")
def energy_to_wavelength(energy):
    """
    Returns photon wavelength (m) for the given energy (J)

    Args:
        energy (float): photon energy (J)
    Returns:
        float: photon wavelength (m)
    """
    return hc / energy


@units(a="m", result="m")
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
    return a / sqrt(h ** 2 + k ** 2 + l ** 2)


@units(theta="rad", d="m", result="m")
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


@units(theta="rad", d="m", result="J")
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


@units(energy="J", d="m", result="rad")
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
    return arcsin(n * hc / (2 * d * energy))


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
    symbol, plane = "", ""
    for c in text:
        if c.isdigit() or c.isspace():
            plane += c
        elif c.isalpha():
            symbol += c
    return globals()[symbol](plane)


class BasePlane(object):
    """
    Base crystal plane.

    This object should not be created directly.
    """

    def __init__(self, distance):
        self.d = distance

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


class CrystalPlane(BasePlane):
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
        (h, k, l), a = self.plane, self.crystal.lattice_constant
        distance = distance_lattice_diffraction_plane(h, k, l, a)
        super(CrystalPlane, self).__init__(distance)

    def __repr__(self):
        return "{}({})".format(self.crystal, self.plane.tostring())

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


class MultiPlane(BasePlane):
    """
    Multi crystal plane.

    Examples::

        >>> from bliss.physics.diffraction import MultiPlane

        >>> my_plane = MultiPlane(distance=5.0e-10)
        >>> e = my_plane.bragg_energy(50e-3)
    """

    def __repr__(self):
        name = type(self).__name__
        return "{}(distance={})".format(name, self.d)


class Crystal(object):
    """
    Cubic crystal.

    Example::

        >>> from bliss.physics.diffraction import Crystal
        >>> from mendeleev import elements
        >>> Si = Crystal(elements.Si)
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


# Export all periodic table element cubic crystals


def _get_all_crystals():
    result = []
    for elem_symbol in elements.__all__:
        elem = getattr(elements, elem_symbol)
        if elem.lattice_constant is not None:
            result.append(Crystal(elem))
    return result


globals().update({c.name: c for c in _get_all_crystals()})
