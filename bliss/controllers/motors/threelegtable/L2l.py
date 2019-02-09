from numpy import eye, pi
from copy import deepcopy
from .Euler2H import euler2H


def L2l(L1, L2, L3):
    """
    L1, L2 and L3 are leg containers

    It returns a set of legs in the right computational order 
    """
    if L1.cmpOrd == 1:
        l1 = deepcopy(L1)
        l1.orig = 1
        L1.rel = 1
    elif L1.cmpOrd == 2:
        l2 = deepcopy(L1)
        l2.orig = 1
        L1.rel = 2
    elif L1.cmpOrd == 3:
        l3 = deepcopy(L1)
        l3.orig = 1
        L1.rel = 3

    if L2.cmpOrd == 1:
        l1 = deepcopy(L2)
        l1.orig = 2
        L2.rel = 1
    elif L2.cmpOrd == 2:
        l2 = deepcopy(L2)
        l2.orig = 2
        L2.rel = 2
    elif L2.cmpOrd == 3:
        l3 = deepcopy(L2)
        l3.orig = 2
        L2.rel = 3

    if L3.cmpOrd == 1:
        l1 = deepcopy(L3)
        l1.orig = 3
        L3.rel = 1
    elif L3.cmpOrd == 2:
        l2 = deepcopy(L3)
        l2.orig = 3
        L3.rel = 2
    elif L3.cmpOrd == 3:
        l3 = deepcopy(L3)
        l3.orig = 3
        L3.rel = 3

    # find the rotation between the world frame and the computation frame for
    # the forward kinematics
    # x = find(l2.fixDof == 1);
    if l2.fixDof[0] == 1:
        # print("Pi/2")
        H = euler2H(0.0, 0.0, pi / 2)
    else:
        # print("identity")
        H = eye(4)

    R = H[:3, :3]
    return l1, l2, l3, L1, L2, L3, R
