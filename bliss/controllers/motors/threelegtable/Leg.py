import numpy


class Leg(object):
    def __init__(self, dof="xyz"):
        self._analyzeDegreesOfFreedom(dof)

    def _analyzeDegreesOfFreedom(self, dof):
        if hasattr(dof, "lower"):
            dof = dof.lower()
        self._cmpOrd = len(dof)
        self._fixDof = [1, 1, 1]
        if "x" in dof:
            self.fixDof[0] = 0
        if "y" in dof:
            self.fixDof[1] = 0
        if "z" in dof:
            self.fixDof[2] = 0
        self._dof = dof

    def get_dof(self):
        return self._dof

    def get_cmpOrd(self):
        return self._cmpOrd

    def get_fixDof(self):
        return self._fixDof

    def get_w(self):
        return self._w.reshape(-1, 1)

    def set_w(self, sequence):
        v = numpy.asarray(sequence, dtype=numpy.float64).reshape(3, 1)
        self._w = v

    def get_s(self):
        return self._s.reshape(-1, 1)

    def set_s(self, sequence):
        v = numpy.asarray(sequence, dtype=numpy.float64).reshape(3, 1)
        self._s = v

    dof = property(get_dof, doc="Degrees of freedom as string")
    cmpOrd = property(get_cmpOrd, doc="Doc to be written")
    fixDof = property(get_fixDof, doc="Degrees of freedom as list")
    w = property(get_w, set_w, doc="Vector of world coordinates")
    s = property(get_s, set_s, doc="Vector of sample coordinates")
