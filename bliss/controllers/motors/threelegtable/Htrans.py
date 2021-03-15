import numpy


def htrans(p):
    if p.size != 3:
        raise IndexError("3D vector expected")
    v = p[:]
    v.shape = -1
    H = numpy.eye(4, dtype=float)
    H[:3, 3] = v
    return H


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 4:
        # print("Usage:")
        # print("htrans x y z")
        sys.exit(0)
    data = numpy.array([float(x) for x in sys.argv[1:]])
    data.shape = 1, -1
    # print(htrans(data))
    data.shape = -1, 1
    # print(htrans(data))
    data.shape = -1
    # print(htrans(data))
