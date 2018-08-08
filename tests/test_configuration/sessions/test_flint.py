# Imports
import numpy
import scipy.misc
from bliss.common.plot import *

# Test data

colored_image = scipy.misc.face()[:10, :10, :]
grey_image = colored_image[:, :, 0]
image_stack = [colored_image[:, :, i] for i in range(3)]

x_data = numpy.linspace(0, 10, 100)
cos_data = numpy.cos(x_data)
sin_data = numpy.sin(x_data)


sin_cos_dict = {
    'x': x_data,
    'sin': sin_data,
    'cos': cos_data}

sin_cos_struct = numpy.array(
    (x_data, sin_data, cos_data),
    dtype=[('x', float, x_data.shape),
           ('sin', float, sin_data.shape),
           ('cos', float, cos_data.shape)])

sin_cos_scan = numpy.array(
    list(zip(x_data, sin_data, cos_data)),
    dtype=[('x', float),
           ('sin', float),
           ('cos', float)])
