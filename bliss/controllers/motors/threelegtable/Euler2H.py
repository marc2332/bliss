import numpy
from numpy import cos, sin


def euler2H(rx, ry, rz):
    xRot = numpy.array(
        [[1.0, 0.0, 0.0], [0.0, cos(rx), -sin(rx)], [0.0, sin(rx), cos(rx)]],
        numpy.float,
    )
    yRot = numpy.array(
        [[cos(ry), 0.0, sin(ry)], [0.0, 1.0, 0.0], [-sin(ry), 0.0, cos(ry)]],
        numpy.float,
    )
    zRot = numpy.array(
        [[cos(rz), -sin(rz), 0.0], [sin(rz), cos(rz), 0.0], [0.0, 0.0, 1.0]],
        numpy.float,
    )
    H = numpy.zeros((4, 4), numpy.float)
    H[:3, :3] = numpy.dot(zRot, numpy.dot(yRot, xRot))
    H[3, 3] = 1.0
    return H


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 4:
        # print("Usage:")
        # print("Euler2H rotX rotY rotZ")
        sys.exit(0)
    rotX, rotY, rotZ = [numpy.float(x) for x in sys.argv[1:]]
    # print(euler2H(rotX, rotY, rotZ))
