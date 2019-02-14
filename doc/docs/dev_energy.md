# Dealing with energy


Bliss provides tools to deal with energy related topics.

`bliss.physics.diffraction` module which is based on `mendeleev`
 [external module](https://mendeleev.readthedocs.io/en/stable/) allows
 to deal with various notions encountered when programming sequences
 for X-Ray experiments:

 * [Elements](#elements)
 * [Crystal and crystal plane](#crystal)
 * [Energy and wavelength](#)

Some functions to calculate usualy associated values are also provided:

 * interplanar distance between lattice planes
 * conversion between energy and wavelength
 * Bragg values:
     * [angle](#bragg-angle)
     * [energy and wavelength](#bragg-energy)


To ease and secure the handling of data in various units, Bliss
provides a module named [units](#units-management-with-units).



## Theory


### De Broglie

$$
\lambda = \frac{h}{p}
$$

where:

 * λ: wavelength
 * *h*: Planck constant
 * *p*: momentum = mass * velocity


### Bragg's law

$$
\lambda = 2.d.sin(\theta)
$$

as
$$
E = mc^2  \qquad  and \qquad  p = mv
$$

$$
\lambda = \frac{hc}{E} \Leftrightarrow E  = \frac{hc}{\lambda} \Leftrightarrow  E = \frac{nhc}{2.d.sin(\theta)}
$$

where:

 * n: order of reflection [1..]
 * λ: wavelength incident angle
 * θ: scattering angle
 * d: interplanar distance between lattice planes


Cubic crystal diffraction

$$
d = \frac{a}{\sqrt{h^2+k^2+l^2}}
$$

## Units management with `units`

When an argument to any function represents a physical quantity, the library
expects the units to be coherent. Passing Quantity objects makes sure you are
coherent.

The implementation is permissive, which means that if you pass a float/int
instead of a Quantity, the library assumes the argument to be in the correct
units which are SI units. Failure to comply will result in unexpected values.


`units` is based on
`pint`[external module](https://pint.readthedocs.io/en/latest/index.html).


### Example

    import bliss.physics.diffraction
    from bliss.physics.units import ur
    mass = 0.1 * ur.mg
    E = mass * ur.c**2
    print( E.to(ur.kJ) )
    >>> 8987551.78737 kilojoule


## Example of usage


### Elements

`mendeleev.elements` usage example:

    from mendeleev import elements
    Si = elements.Si
    print("Atomic number of {} is {}.".format(Si.name, Si.atomic_number))
    >>> Atomic number of Silicon is 14.


### Crystal

Cubic crystal:

    from bliss.physics.diffraction import Crystal
    from mendeleev import elements
    Si = Crystal(elements.Si)
    Si111 = Si('111')
    Si111
    >>> Si(111)


Most crystals are already available at the module level so you rarely
need to create an instance of this class:

    bliss.physics.diffraction.Si
    >>> Si

    bliss.physics.diffraction.Ge
    >>> Ge


Crystal Plane:

    from bliss.physics.diffraction import CrystalPlane
    Si110 = CrystalPlane.fromstring('Si110')


### Bragg angle ###


How to find the bragg angle (in degrees) for a silicon crystal at the
110 plane when the energy is 12.5 keV:

    from bliss.physics.units import ur
    from bliss.physics.diffraction import Si
    keV, deg = ur.keV, ur.deg
    Si110 = Si('110')
    energy = 12.5*keV
    angle = Si110.bragg_angle(energy)
    
    # angle is a Quantity (radians)
    print( angle )
    >>> 0.12952587191 radian
    
    # view it as a Quantity (degrees)
    print( angle.to(deg) )
    >>> 7.42127016 degree
    
    # get the float in degrees
    print( angle.to('deg').magnitude )
    >>> 7.42127016

### Bragg energy ###

How to find the bragg energy (keV) for a germanium crystal at 444
plane when the angle is 25.6 degrees:

    from bliss.physics.diffraction import Ge
    deg = ur.deg
    
    Ge444 = Ge('444')
    angle = 25.6*deg
    energy = Ge444.bragg_energy(angle)
    wavelength = Ge444.bragg_wavelength(angle)
    
    energy
    >>> <Quantity(2.81372042834e-15, 'joule')>
    
    wavelength
    >>> <Quantity(7.05985450176e-11, 'meter')>
    
    print( energy.to(keV) )
    >>> 17.5618627264 kiloelectron_volt
    
    print( energy.to(ur.keV).magnitude )
    >>> 17.5618627264

