from bliss.controllers.motor import CalcController


class Slits(CalcController):

    def __init__(self, *args, **kwargs):
        CalcController.__init__(self, *args, **kwargs)

    def calc_from_real(self, positions_dict):
        return {
            "hoffset": (
                positions_dict["back"] -
                positions_dict["front"]) /
            2.0,
            "hgap": positions_dict["back"] +
            positions_dict["front"],
            "voffset": (
                positions_dict["up"] -
                positions_dict["down"]) /
            2.0,
            "vgap": positions_dict["up"] +
            positions_dict["down"]}

    def calc_to_real(self, axis_tag, positions_dict):
        if axis_tag in ("hoffset", "hgap"):
            return {
                "back": (
                    positions_dict["hoffset"] /
                    2.0) +
                positions_dict["hgap"],
                "front": (
                    positions_dict["hgap"] /
                    2.0) -
                positions_dict["hoffset"]}
        elif axis_tag in ("voffset", "vgap"):
            return {
                "up": (
                    positions_dict["voffset"] /
                    2.0) +
                positions_dict["vgap"],
                "down": (
                    positions_dict["vgap"] /
                    2.0) -
                positions_dict["voffset"]}
