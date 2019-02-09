import numpy
from numpy import cos, sin, sqrt, eye, arctan2, arcsin, arccos, concatenate
from numpy.linalg import norm
from .L2l import L2l
from .Htrans import htrans
from .Euler2H import euler2H

DEBUG = 1


def fwdKin(leg1, leg2, leg3):
    if DEBUG:
        # print("RECEIVED")
        # print("leg1")
        # print("w", leg1.w)
        # print("s", leg1.s)
        # print("leg2")
        # print("w", leg2.w)
        # print("s", leg2.s)
        # print("leg3")
        # print("w", leg3.w)
        # print("s", leg3.s)
        pass

    # define the positions of the jacks in a normaized coordinte frame
    l1, l2, l3, L1, L2, L3, R = L2l(leg1, leg2, leg3)

    # find the right computation order and the orientation of the computation frame

    # put the legs in the computation frame
    l1.w = numpy.dot(R, l1.w)
    l2.w = numpy.dot(R, l2.w)
    l3.w = numpy.dot(R, l3.w)

    # compute the forward kinematics
    u = numpy.array(
        [L1.u, L2.u, L3.u], dtype=numpy.float
    )  # get the z positions of the jacks
    du = u - u[0]  # get the differential position of the jacks

    # step1: compute the postion of the axis which has one additional dof
    if DEBUG:
        # print("u")
        # print(u)
        # print("du")
        # print(du)
        # print('fwdKin step1')
        pass

    dab = l2.w - l1.w
    dab_1 = l2.w[0] - l1.w[0]
    # dab_2 = l2.w[1] - l1.w[1]
    dab_3 = l2.w[2] - l1.w[2]

    dac = l3.w - l1.w
    dac_1 = l3.w[0] - l1.w[0]
    dac_2 = l3.w[1] - l1.w[1]
    dac_3 = l3.w[2] - l1.w[2]

    dbc = l3.w - l2.w
    dbc_1 = l3.w[0] - l2.w[0]
    dbc_2 = l3.w[1] - l2.w[1]
    dbc_3 = l3.w[2] - l2.w[2]

    dbB_3 = du[1]
    dcC_3 = du[2]

    dbB_1 = -dab_1 + sqrt(pow(dab_1, 2) - (2 * dab_3 * dbB_3 + pow(dbB_3, 2)))
    if hasattr(dbB_1, "__len__"):
        dbB_1 = dbB_1[0]
    if hasattr(dbB_3, "__len__"):
        dbB_3 = dbB_3[0]

    daB = dab + numpy.array([dbB_1, 0, dbB_3]).reshape(-1, 1)

    if DEBUG:
        # print("daB")
        # print(daB)
        # print('fwdKin step2')
        pass

    a1 = dac_1[0]
    a2 = dac_2[0]
    a3 = (pow(dac_3 + dcC_3, 2) - pow(norm(dac), 2))[0]
    b1 = (-dbB_1 + dbc_1)[0]
    b2 = dbc_2[0]
    b3 = (pow(-dbB_3 + dbc_3 + dcC_3, 2) - pow(norm(dbc), 2))[0]

    # print(a1, a2, a3)
    # print(b1, b2 , b3)

    # the nonlinear constrains are the following
    # 0 = (a1 + dcC_1)^2 + (a2 + dcC_2)^2 + a3;
    # 0 = (b1 + dcC_1)^2 + (b2 + dcC_2)^2 + b3;
    # use the newton methode for solving this problem
    x = numpy.zeros((2, 1), numpy.float)  # starting value with x = [dcC_1; dcC_2]
    for k in range(100):
        J = numpy.array(
            [
                [2 * a1 + 2 * x[0, 0], 2 * a2 + 2 * x[1, 0]],
                [2 * b1 + 2 * x[0, 0], 2 * b2 + 2 * x[1, 0]],
            ],
            dtype=numpy.float,
        )
        F = numpy.array(
            [
                (a1 + x[0, 0]) ** 2 + (a2 + x[1, 0]) ** 2 + a3,
                (b1 + x[0, 0]) ** 2 + (b2 + x[1, 0]) ** 2 + b3,
            ],
            dtype=numpy.float,
        ).reshape(2, 1)
        x = x - numpy.dot(numpy.linalg.inv(J), F)

    daC = dac + numpy.array([x[0, 0], x[1, 0], dcC_3], dtype=numpy.float).reshape(3, 1)
    # print("daC")
    # print(daC)

    dBC = -daB + daC

    if DEBUG:
        # print([x[0], x[1], dcC_3])
        # print('fwdKin step3')
        pass

    dab = numpy.dot(R.T, dab).reshape(-1)
    dac = numpy.dot(R.T, dac).reshape(-1)
    daB = numpy.dot(R.T, daB).reshape(-1)
    daC = numpy.dot(R.T, daC).reshape(-1)
    dBC = numpy.dot(R.T, dBC).reshape(-1)
    l1.w = numpy.dot(R.T, l1.w)
    l2.w = numpy.dot(R.T, l2.w)
    l3.w = numpy.dot(R.T, l3.w)
    if DEBUG:
        # print("FINAL STEP 3")
        # print("l1")
        # print("w", leg1.w)
        # print("l")
        # print("w", leg2.w)
        # print("l3")
        # print("w", leg3.w)
        # print('fwdKin step4')
        # print("dab = ", dab)
        pass

    # find elements of the rotation matrix
    if (dab[2] == 0) and (dac[2] == 0) and (dbc[2] == 0):
        # if there is no difference in z-direction of the joint points
        U = numpy.concatenate(
            (
                numpy.concatenate((eye(3) * dab[0], eye(3) * dab[1]), axis=1),
                numpy.concatenate((eye(3) * dac[0], eye(3) * dac[1]), axis=1),
            ),
            axis=0,
        )
        Y = numpy.concatenate((daB, daC), axis=0)
    else:
        # if there are differences in the z-direction of the joint points
        U = concatenate(
            (
                concatenate(
                    (eye(3) * dab[0], eye(3) * dab[1], eye(3) * dab[2]), axis=1
                ),
                concatenate(
                    (eye(3) * dac[0], eye(3) * dac[1], eye(3) * dac[2]), axis=1
                ),
                concatenate(
                    (eye(3) * dbc[0], eye(3) * dbc[1], eye(3) * dbc[2]), axis=1
                ),
            ),
            axis=0,
        )
        Y = numpy.concatenate((daB, daC, dBC), axis=0)
    if DEBUG:
        # print("U = ", U)
        # print(U.shape)
        # print("Y = ", Y)
        # print(Y.shape)
        pass

    R = numpy.dot(numpy.linalg.inv(U), Y)

    if DEBUG:
        # print("R = ", R)
        # print("shape = ", R.shape)
        pass

    rz = arctan2(R[1], R[4])
    rx = arccos(R[4] / cos(rz))

    if du[2] < 0:
        rx = -rx

    # print("rz = ", rz)
    # print("rx = ", rx)
    csry = numpy.array(
        [[cos(rz), sin(rx) * sin(rz)], [sin(rx) * sin(rz), -cos(rz)]], dtype=numpy.float
    )
    csry = numpy.dot(
        numpy.linalg.inv(csry), numpy.concatenate((R[0:1], R[2:3]), axis=0)
    )
    ry = arctan2(csry[1], csry[0])

    # step5: find the z position of the plain
    if DEBUG:
        # print('fwdKin step5')
        pass

    Hs = numpy.dot(
        htrans(l1.w),
        numpy.dot(euler2H(rx, ry, 0), numpy.dot(euler2H(0, 0, rz), htrans(-l1.s))),
    )
    z = Hs[2, 3] + u[0]

    if DEBUG:
        # print("returning z, rx, ry, rz")
        # print(z, rx, ry, rz)
        pass

    return z, rx, ry, rz
