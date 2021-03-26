import numpy
import gi

gi.require_version("Hkl", "5.0")
from gi.repository import Hkl


def matrix_to_numpy(mat):
    arr = numpy.zeros((3, 3), numpy.float64)
    for i in range(3):
        for j in range(3):
            arr[i, j] = mat.get(i, j)
    return arr


def numpy_to_matrix(arr):
    mat = Hkl.Matrix.new_euler(0., 0., 0.)
    Hkl.Matrix.init(
        mat,
        arr[0][0],
        arr[0][1],
        arr[0][2],
        arr[1][0],
        arr[1][1],
        arr[1][2],
        arr[2][0],
        arr[2][1],
        arr[2][2],
    )
    return mat


#    for i in range(3):
#        for j in range(3):
#            mat.set(i, j, arr[i,j])


def get_version():
    return Hkl._version


def get_new_detector():
    detector = Hkl.Detector.factory_new(Hkl.DetectorType(0))
    return detector


def get_geometry_list():
    return " ".join(list(Hkl.factories().keys()))


def get_geometry_positions(
    geometry, unit
):  # geometry is the low level obj from Hkl =====
    axis_names = geometry.axis_names_get()
    axis_values = geometry.axis_values_get(unit)
    axis_pos = dict()
    for (name, pos) in zip(axis_names, axis_values):
        axis_pos[name] = pos
    return axis_pos


def set_geometry_positions(geometry, pos_dict, unit):
    axis_names = geometry.axis_names_get()
    axis_values = geometry.axis_values_get(unit)
    for (name, pos) in list(pos_dict.items()):
        try:
            idx = axis_names.index(name)
        except ValueError:
            raise ValueError("Invalid axis name [{0}].".format(name))
        axis_values[idx] = pos
    geometry.axis_values_set(axis_values, unit)
