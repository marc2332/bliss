import pytest

from numpy import sin, sqrt, pi

from bliss.physics.units import ur, units

# shortcuts

h, c = ur.h, ur.c
m, cm = ur.m, ur.cm
kg, g = ur.kg, ur.g
s = ur.s
J = ur.J
rad = ur.rad


def test_units_decorator_errors():

    with pytest.raises(TypeError):

        @units("J", "kg")
        def E_err1(mass):
            return mass * c ** 2

    with pytest.raises(TypeError):

        @units(mess="kg")
        def E_err2(mass):
            return mass * c ** 2

    with pytest.raises(TypeError):

        @units(mass="kg", mess="J")
        def E_err3(mass):
            return mass * c ** 2

    @units(mass=kg, result=J)
    def E_err4(mass):
        return 0

    with pytest.raises(TypeError):
        E_err4(1)


def test_units_decorator_1_arg():

    # string params

    @units(d1="m", result="m")
    def twice(d1):
        return 2.0 * d1

    assert type(twice(5.0)) == float
    assert twice(5.0) == 10.0
    assert twice(0.1 * m) == 0.2 * m
    assert twice(45 * cm) == 0.9 * m

    # quantity params

    @units(mass=kg, result=J)
    def E(mass):
        return mass * c ** 2

    assert type(E(10)) == float
    assert E(10) == (10 * kg * c ** 2).to(J).magnitude
    assert type(E(10 * g)) == ur.Quantity
    assert E(10 * g) == (10 * g * c ** 2).to(J)


def test_units_decorator_n_args():
    @units(p1=m / s, p2=m / s, result=m / s)
    def sum_speeds1(p1, p2):
        return p1 + p2

    assert type(sum_speeds1(10.0, -5.0)) == float
    assert sum_speeds1(10.0, -5.0) == 5.0
    assert sum_speeds1(10.0 * m / s, -5.0) == 5.0 * m / s
    assert sum_speeds1(10.0 * m / s, -5.0 * m / s) == 5.0 * m / s

    @units(p1=m / s, result=m / s)
    def sum_speeds2(p1, p2):
        return p1

    assert type(sum_speeds2(10.0, -5.0)) == float
    assert sum_speeds2(10.0, -5.0) == 10.0
    assert sum_speeds2(10.0 * m / s, -5.0) == 10.0 * m / s
    assert sum_speeds2(10.0, -5.0 * m / s) == 10.0


def test_inner_calls():
    @units(wavelength=m, result=J)
    def wavelength_to_energy(wavelength):
        return h * c / wavelength

    @units(theta=rad, d=m, result=m)
    def bragg_wavelength(theta, d, n=1):
        return 2 * d * sin(theta) / n

    @units(a=m)
    def distance(h, k, l, a):
        return a / sqrt(h ** 2 + k ** 2 + l ** 2)

    @units(theta=rad, d=m, result=J)
    def bragg_energy(theta, d, n=1):
        return wavelength_to_energy(bragg_wavelength(theta, d, n=n))

    def bragg_energy_units(theta, d, n=1):
        q = h * c / (2 * d * m * sin(theta * rad) / n)
        return q.to("J")

    f_Si_a = 5.43e-10
    f_Si110_d = f_Si_a / sqrt(1 ** 2 + 1 ** 2 + 0 ** 2)
    f_theta = pi / 8
    f_energy = bragg_energy_units(f_theta, f_Si110_d).magnitude

    q_Si_a = f_Si_a * m
    q_Si110_d = f_Si110_d * m
    q_theta = f_theta * rad
    q_energy = f_energy * J

    assert bragg_energy(f_theta, f_Si110_d) == f_energy
    assert bragg_energy(q_theta, f_Si110_d) == q_energy
    assert bragg_energy(f_theta, q_Si110_d) == q_energy
    assert bragg_energy(q_theta, q_Si110_d) == q_energy
