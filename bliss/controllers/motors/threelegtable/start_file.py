import numpy
from Leg import Leg


class Sample(object):
    pass


__doc__ = """This script computes the forward kinematics for a table with three three vertical legs."""

# define the degrees of freedom of the legs
# --> leg 1 can only move in z direction
# L1.dof = 'z';
leg1 = Leg("z")

# --> leg 2 can move in x and z direction
# L2.dof = 'xz';
leg2 = Leg("xz")

# --> leg 3 can move in x, y and z direction
# L3.dof = 'xyz';
leg3 = Leg("xyz")

# define the position of the three legs in the world coordinates
# --> position of leg 1 (=> L1) in the world frame (w)
leg1.w = numpy.asarray([0.1, -0.2, 0], dtype=numpy.float64)

# --> position of leg 2 (=> L2) in the world frame (w)
leg2.w = numpy.asarray([-0.1, -0.1, 0], dtype=numpy.float64)

# --> position of leg 3 (=> L3) in the world frame (w)
leg3.w = numpy.asarray([0, 0.2, 0], dtype=numpy.float64)


# define the position of the three legs in the sample coordinates
# --> position of leg 1 (=> L1) in the sample frame (s)
leg1.s = numpy.asarray([0.1, -0.2, 0], dtype=numpy.float64)

# --> position of leg 2 (=> L2) in the sample frame (s)
leg2.s = numpy.asarray([-0.1, -0.1, 0], dtype=numpy.float64)

# --> position of leg 3 (=> L3) in the sample frame (s)
leg3.s = numpy.asarray([0, 0.2, 0], dtype=numpy.float64)

# define the desired sample position and orientation
sample = Sample()
sample.z = 0000  # z position in [m]
sample.rx = 0.020  # rotation about x in [rad]
sample.ry = 0.0000  # rotation about y in [rad]


if 0:
    import sys
    from Htrans import htrans

    print(htrans(leg3.s))
    print(htrans(leg2.w))
    print(numpy.dot(numpy.linalg.inv(htrans(leg3.s)), htrans(leg2.w)))
    sys.exit(0)

if 0:
    from L2l import L2l

    print("BEFORE")
    print("L1w", leg1.w)
    print("L1s", leg1.s)
    l1, l2, l3, L1, L2, L3, R = L2l(leg1, leg2, leg3)
    print("AFTER")
    print("L1w", leg1.w)
    print("L1s", leg1.s)
    sys.exit(0)
# ------------------------------------------------------------------------
#  ########## Computation of inverse Kinematics ###########################
#  ------------------------------------------------------------------------
from InvKin import invKin

[L1, L2, L3] = invKin(leg1, leg2, leg3, sample)

# ------------------------------------------------------------------------
#  ########## Computation of forward Kinematics ###########################
#  ------------------------------------------------------------------------
from FwdKin import fwdKin

[z, rx, ry, rz] = fwdKin(L1, L2, L3)
