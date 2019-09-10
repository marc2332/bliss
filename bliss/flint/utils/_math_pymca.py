import numpy

ODD_SIGN = 1.0
__LAST_COEFF = None


def calc_coeff(num_points, pol_degree, diff_order=0):
    """
    Calculates filter coefficients for symmetric savitzky-golay filter.
    see: http://www.nrbook.com/a/bookcpdf/c14-8.pdf

    num_points   means that 2*num_points+1 values contribute to the
                 smoother.

    pol_degree   is degree of fitting polynomial

    diff_order   is degree of implicit differentiation.
                 0 means that filter results in smoothing of function
                 1 means that filter results in smoothing the first
                                             derivative of function.
                 and so on ...
    """
    global __LAST_COEFF
    global __LAST_NUM_POINTS
    global __LAST_POL_DEGREE
    global __LAST_DIFF_ORDER
    if __LAST_COEFF is not None:
        if num_points == __LAST_NUM_POINTS:
            if pol_degree == __LAST_POL_DEGREE:
                if diff_order == __LAST_DIFF_ORDER:
                    return __LAST_COEFF
    else:
        __LAST_NUM_POINTS = num_points
        __LAST_POL_DEGREE = pol_degree
        __LAST_DIFF_ORDER = diff_order

    # setup interpolation matrix
    # ... you might use other interpolation points
    # and maybe other functions than monomials ....

    x = numpy.arange(-num_points, num_points + 1, dtype=numpy.int)
    monom = lambda x, deg: pow(x, deg)

    A = numpy.zeros((2 * num_points + 1, pol_degree + 1), numpy.float)
    for i in range(2 * num_points + 1):
        for j in range(pol_degree + 1):
            A[i, j] = monom(x[i], j)

    # calculate diff_order-th row of inv(A^T A)
    ATA = numpy.dot(A.transpose(), A)
    rhs = numpy.zeros((pol_degree + 1,), numpy.float)
    rhs[diff_order] = 1
    wvec = numpy.linalg.solve(ATA, rhs)

    # calculate filter-coefficients
    coeff = numpy.dot(A, wvec)
    if (ODD_SIGN < 0) and (diff_order % 2):
        coeff *= ODD_SIGN

    __LAST_COEFF = coeff
    return coeff


def getSavitzkyGolay(spectrum, npoints=3, degree=1, order=0):
    coeff = calc_coeff(npoints, degree, order)
    N = numpy.size(coeff - 1) // 2
    if order < 1:
        result = 1.0 * spectrum
    else:
        result = 0.0 * spectrum
    result[N:-N] = numpy.convolve(spectrum, coeff, mode="valid")
    return result


if getSavitzkyGolay(10 * numpy.arange(10.), npoints=3, degree=1, order=1)[5] < 0:
    ODD_SIGN = -1
    __LAST_COEFF = None


def derivate(xdata, ydata, xlimits=None):
    x = numpy.array(xdata, copy=False, dtype=numpy.float)
    y = numpy.array(ydata, copy=False, dtype=numpy.float)
    if xlimits is not None:
        i1 = numpy.nonzero((xdata >= xlimits[0]) & (xdata <= xlimits[1]))[0]
        x = numpy.take(x, i1)
        y = numpy.take(y, i1)
    i1 = numpy.argsort(x)
    x = numpy.take(x, i1)
    y = numpy.take(y, i1)
    deltax = x[1:] - x[:-1]
    i1 = numpy.nonzero(abs(deltax) > 0.0000001)[0]
    x = numpy.take(x, i1)
    y = numpy.take(y, i1)
    minDelta = deltax[deltax > 0]
    if minDelta.size:
        minDelta = minDelta.min()
    else:
        # all points are equal
        minDelta = 1.0
    xInter = numpy.arange(x[0] - minDelta, x[-1] + minDelta, minDelta)
    yInter = numpy.interp(xInter, x, y, left=y[0], right=y[-1])
    if len(yInter) > 499:
        npoints = 5
    else:
        npoints = 5
    degree = 2
    order = 1
    coeff = calc_coeff(npoints, degree, order)
    N = int(numpy.size(coeff - 1) / 2)
    yInterPrime = numpy.convolve(yInter, coeff, mode="valid") / minDelta
    i1 = numpy.nonzero((x >= xInter[N + 1]) & (x <= xInter[-N]))[0]
    x = numpy.take(x, i1)
    result = numpy.interp(
        x,
        xInter[(N + 1) : -N],
        yInterPrime[1:],
        left=yInterPrime[1],
        right=yInterPrime[-1],
    )
    return x, result
