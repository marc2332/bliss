# Imports
import numpy
import scipy.misc
from bliss.common.plot import *

# Test data

colored_image = scipy.misc.face()
grey_image = colored_image[:, :, 0]
image_stack = [colored_image[:, :, i] for i in range(3)]

x_data = numpy.linspace(0, 10, 1000)
cos_data = numpy.cos(x_data)
sin_data = numpy.sin(x_data)


sin_cos_dict = {
    'x': x_data,
    'cos': cos_data,
    'sin': sin_data}

sin_cos_struct = numpy.array(
    (x_data, cos_data, sin_data),
    dtype=[('x', float, x_data.shape),
           ('cos', float, cos_data.shape),
           ('sin', float, sin_data.shape)])
