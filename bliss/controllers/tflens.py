import numpy
import itertools
import tabulate

from bliss.common.utils import autocomplete_property


class TFLensMaterialGroup:
    def __init__(self, material, lens_id, lens_nb):
        self.material = material
        self.lens_id = lens_id
        self.lens_nb = numpy.array(lens_nb, int)
        self.naxis = len(lens_id)

        # --- axis bit values and mask
        self.axis_id = 1 << numpy.array(self.lens_id, int)
        self.mask = numpy.sum(self.axis_id)

        # --- build all possible combinations array
        # index 0 : number of lenses
        # index 1 : axis value
        values = numpy.zeros(((2 ** self.naxis), 2), int)
        validx = 0
        for combination in itertools.product(range(2), repeat=self.naxis):
            comb_arr = numpy.array(combination)
            values[validx, 0] = numpy.sum(comb_arr * self.lens_nb)
            values[validx, 1] = numpy.sum(comb_arr * self.axis_id)
            validx += 1

        # --- removes duplicates and sort
        self.data = numpy.unique(values, axis=0)

    def lens2name(self, lens_id):
        if lens_id in self.lens_id:
            index = self.lens_id.index(lens_id)
            return "{0:s}{1:d}".format(self.material, self.lens_nb[index])
        raise None

    def __find_index(self, tf_state):
        value = tf_state & self.mask
        try:
            return numpy.where(self.data[:, 1] == value)[0][0]
        except IndexError:
            raise ValueError(
                f"No corresponding {self.material} lens value for transfocator state [{tf_state}]"
            )

    def state2lensnb(self, tf_state):
        index = self.__find_index(tf_state)
        return self.data[index, 0]

    def state2upvalue(self, tf_state):
        index = self.__find_index(tf_state)
        if index < self.data.shape[0] - 1:
            return self.data[index + 1, 1]
        else:
            raise ValueError(f"{self.material} lens number already at maximum.")

    def state2downvalue(self, tf_state):
        index = self.__find_index(tf_state)
        if index > 0:
            return self.data[index - 1, 1]
        else:
            raise ValueError(f"{self.material} lens number already zero.")

    def lens2value(self, lensnb):
        if lensnb < 0:
            lensnb = 0
        lensmax = self.data[:, 0].max()
        if lensnb > lensmax:
            raise ValueError(f"Maximum number of {self.material} lenses is {lensmax}")
        try:
            index = numpy.where(self.data[:, 0] == lensnb)[0][0]
            return self.data[index, 1]
        except IndexError:
            indmin = numpy.where(self.data[:, 0] < lensnb)[0][-1]
            valmin = self.data[indmin, 0]
            indmax = numpy.where(self.data[:, 0] > lensnb)[0][0]
            valmax = self.data[indmax, 0]
            raise ValueError(
                f"No corresponding {self.material} number of lenses\n"
                f"Closest possible values are {valmin} and {valmax}"
            )


class TFLens:
    def __init__(self, name, config):
        self.name = name

        if "transfocator" not in config:
            raise ValueError(f'Need to specify "transfocator" TFLens [{name}]')
        if "lenses" not in config:
            raise ValueError(f'Need to specify "lenses" for TFLens [{name}]')

        self.__transfocator = config.get("transfocator")
        self.__lens_def = list()

        lensconfig = config.get("lenses")
        for lensdef in lensconfig:
            material = lensdef.get("material", None)
            lens_id = lensdef.get("lens_id", None)
            lens_nb = lensdef.get("lens_nb", None)
            if material is None or lens_id is None or lens_nb is None:
                raise ValueError(f'Incomplete "lenses" definition for TFLens [{name}]')
            if len(lens_id) != len(lens_nb):
                raise ValueError(
                    f"TFLens [{name}] material [{material}] : lens_nb and lens_id should have the same size"
                )
            self.__lens_def.append(TFLensMaterialGroup(material, lens_id, lens_nb))

        self.ntflens = self.__transfocator.nb_lens + self.__transfocator.nb_pinhole

    @autocomplete_property
    def transfocator(self):
        return self.__transfocator

    def __set_pinhole(self, inout):
        if not self.__transfocator.nb_pinhole:
            raise RuntimeError("Transfocator has no pinhole defined !!")
        self.__transfocator.set_pin(inout)

    def pin(self):
        self.__set_pinhole(True)

    def pout(self):
        self.__set_pinhole(False)

    def setin(self, *lens_ids):
        ids = self.__check_lensid(lens_ids)
        tfset = self.transfocator.pos_read()
        for lid in ids:
            tfset |= 1 << lid
        self.transfocator.set_bitvalue(tfset)

    def setout(self, *lens_ids):
        ids = self.__check_lensid(lens_ids)
        tfset = self.transfocator.pos_read()
        for lid in ids:
            tfset = tfset & (~(1 << lid))
        self.transfocator.set_bitvalue(tfset)

    def __check_lensid(self, lens_ids):
        allids = list(range(self.ntflens))
        if not len(lens_ids):
            return allids
        for lid in lens_ids:
            if lid not in allids:
                raise ValueError(f"Invalid lens id. Should be in {allids}")
        return lens_ids

    @property
    def materials(self):
        return tuple(lens.material for lens in self.__lens_def)

    def __find_lens_group(self, material=None):
        if material is None:
            if len(self.__lens_def) == 1:
                return self.__lens_def[0]
            else:
                raise ValueError(f"Need to specify lens material in {self.materials}")
        for lens in self.__lens_def:
            if lens.material.lower() == material.lower():
                return lens
        raise ValueError(f"Not lens group for material [{material}]")

    def zero(self, material=None):
        if material is None:
            mask = 0
            for lens in self.__lens_def:
                mask |= lens.mask
            tfget = self.transfocator.pos_read()
            tfset = tfget & (~mask)
            self.transfocator.set_bitvalue(tfset)
        else:
            self.set(0, material)

    def set(self, nlenses, material=None):
        lens = self.__find_lens_group(material)
        tfset = lens.lens2value(nlenses)
        tfget = self.transfocator.pos_read()
        tfset = (tfget & (~lens.mask)) | tfset
        self.transfocator.set_bitvalue(tfset)

    def get(self, material=None):
        lens = self.__find_lens_group(material)
        tfget = self.transfocator.pos_read()
        return lens.state2lensnb(tfget)

    def getlenses(self):
        alllens = dict()
        tfget = self.transfocator.pos_read()
        for lens in self.__lens_def:
            alllens[lens.material] = lens.state2lensnb(tfget)
        return alllens

    def setlenses(self, dict_values):
        tfval = self.transfocator.pos_read()
        for (material, value) in dict_values.items():
            lens = self.__find_lens_group(material)
            tfset = lens.lens2value(value)
            tfval = (tfval & (~lens.mask)) | tfset
        self.transfocator.set_bitvalue(tfval)

    def up(self, material=None):
        self.__set_updown(1, material)

    def down(self, material=None):
        self.__set_updown(-1, material)

    def __set_updown(self, updown, material=None):
        lens = self.__find_lens_group(material)
        tfget = self.transfocator.pos_read()
        if updown > 0:
            tfset = lens.state2upvalue(tfget)
        else:
            tfset = lens.state2downvalue(tfget)
        tfset = (tfget & (~lens.mask)) | tfset
        self.transfocator.set_bitvalue(tfset)

    def __lens2names(self):
        names = list()
        for lid in range(self.ntflens):
            name = f"L{lid}"
            if lid in self.transfocator.pinhole:
                name = f"P{lid}"
            for lens in self.__lens_def:
                if lid in lens.lens_id:
                    name = lens.lens2name(lid)
            names.append(name)
        return names

    def __lens2ids(self):
        return [f"#{lid}" for lid in range(self.ntflens)]

    def __tfstate2string(self, value):
        states = list()
        for lid in range(self.ntflens):
            if value & (1 << lid):
                states.append("IN")
            else:
                states.append("OUT")
        return states

    def status(self):
        print(self.__info__())

    def __info__(self):
        tfstate = self.transfocator.pos_read()
        info = ""
        ids = self.__lens2ids()
        names = self.__lens2names()
        states = self.__tfstate2string(tfstate)
        info += tabulate.tabulate([ids, names, states], tablefmt="plain")
        info += "\n\n"

        for lens in self.__lens_def:
            info += "{0:s} = {1:d} lenses IN\n".format(
                lens.material, lens.state2lensnb(tfstate)
            )
        return info
