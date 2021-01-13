import numpy
from numpy import cos, sin
from .L2l import L2l
from .Htrans import htrans
from .Euler2H import euler2H

DEBUG = 0


def invKin(leg1, leg2, leg3, sample):
    l1, l2, l3, L1, L2, L3, R = L2l(leg1, leg2, leg3)
    if DEBUG:
        # print("l1")
        # print(l1.w)
        # print(l1.s)
        # print(l1.fixDof)
        # print(L1.fixDof)
        # print("l2")
        # print(l2.w)
        # print(l2.s)
        # print(l2.fixDof)
        # print(L2.fixDof)
        # print("l3")
        # print(l3.w)
        # print(l3.s)
        # print(l3.fixDof)
        # print(L3.fixDof)
        pass

    # find the position of the sample in the world frame
    w2s = numpy.dot(numpy.linalg.inv(htrans(l1.s)), htrans(l1.w))
    if DEBUG:
        # print("w2s")
        # print(w2s)
        pass

    # find the rotation about the z-axis by the constrain of the second
    # actuator:
    dw = l1.w - l2.w
    ds = l2.s - l1.s
    cx = numpy.cos(sample.rx)
    sx = numpy.sin(sample.rx)
    cy = numpy.cos(sample.ry)
    sy = numpy.sin(sample.ry)

    # if (find(l2.fixDof == 1) == 2)
    if (l2.fixDof[0] == 0) and (l2.fixDof[1] == 1):
        if DEBUG:
            # print("CASE A")
            pass

        # if the y axis is blocked
        rz = 0

        # use newton methode to find the solution
        for k in range(100):
            J = cx * (ds[0] * cos(rz) - ds[1] * sin(rz))
            F = dw[1] - ds[2] * sx + cx * (ds[1] * cos(rz) + ds[0] * sin(rz))
            rz = rz - F / J

    elif l2.fixDof[0] == 1:
        if DEBUG:
            # print("CASE B")
            pass

        # if the x axis is blocked
        rz = 0

        # use newton methode to find the solution
        for k in range(100):
            J = sx * sy * (ds[0] * cos(rz) - ds[1] * sin(rz)) - cy * (
                ds[1] * cos(rz) + ds[0] * sx
            )
            F = (
                dw[0]
                + cy * (ds[0] * cos(rz) - ds[1] * sin(rz))
                + cx * ds[2] * sy
                + sx * sy * (ds[1] * cos(rz) + ds[0] * sin(rz))
            )
            rz = rz - F / J

    else:
        raise ValueError(
            "Error one actuator has not only one degree of freedom in x or y direction"
        )

    if DEBUG:
        # print('rotation about z = ', rz)
        # print('errorvalue in not desired motion= ', F)
        pass

    # define the rotation to the desired rotation
    R = numpy.dot(euler2H(sample.rx, sample.ry, 0.0), euler2H(0.0, 0.0, rz))
    if DEBUG:
        # print("R")
        # print(R)
        pass

    H = numpy.dot(htrans(l1.w), numpy.dot(R, htrans(-l1.s)))
    if DEBUG:
        # print("H")
        # print(H)
        pass

    H_l2 = numpy.dot(htrans(-l2.w), numpy.dot(H, htrans(l2.s)))
    H_l3 = numpy.dot(htrans(-l3.w), numpy.dot(H, htrans(l3.s)))

    if DEBUG:
        # print("H_l3")
        # print(H_l3)
        pass

    s2H = numpy.dot(numpy.linalg.inv(w2s), H)
    dz = sample.z - s2H[2, 3]

    Tz = [dz, dz + H_l2[2, 3], dz + H_l3[2, 3]]
    Ty = [0, H_l2[1, 3], H_l3[1, 3]]
    Tx = [0, H_l2[0, 3], H_l3[0, 3]]

    L1.tz = [Tx[L1.rel - 1], Ty[L1.rel - 1], Tz[L1.rel - 1]]
    L2.tz = [Tx[L2.rel - 1], Ty[L2.rel - 1], Tz[L2.rel - 1]]
    L3.tz = [Tx[L3.rel - 1], Ty[L3.rel - 1], Tz[L3.rel - 1]]

    L1.u = L1.tz[2]
    L2.u = L2.tz[2]
    L3.u = L3.tz[2]
    if DEBUG:
        # print("Lx.u")
        # print(L1.u)
        # print(L2.u)
        # print(L3.u)
        pass

    return L1, L2, L3
