# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Helper class to format a table"""


class IncrementalTable:
    """Manage a table of row data created incrementally.

    Previously known as: FormatedTab

    The row data is not fully available, and the display have to be progressive.

    Arguments:
        header_lines (2D list): list of lines, each line is a list of words (labels).
                                All lines must have the same number of words. 
        minwidth: the minimum width for columns
        maxwidth: the maximum width for columns
        col_sep: the column separator character
        dtype: format for numerical values (f, g, e)
        align: alignment style [ center = '^', left = '<', right = '>' ]
        flag: [ default form = '', alternate form = '#'] 
        ellipse: characters to use for truncated labels
        fpreci: precision for floating point numbers (eg: '.3' for 3 digits precision)
        lmargin: left margin of the entire table
    """

    class _Cell:
        def __init__(
            self,
            value,
            dtype="g",
            align="^",
            width=12,
            flag="#",
            ellipse="..",
            fpreci="",
        ):

            self.value = value
            self.params = {
                "dtype": dtype,
                "align": align,
                "width": width,
                "flag": flag,  # '' or '#'
                "ellipse": ellipse,
                "fpreci": fpreci,  # '' or '.3' for example
            }

        def __str__(self):

            if isinstance(self.value, (int, float)):
                txt = f"{self.value:{self.params['flag']}{self.params['fpreci']}{self.dtype}}"
            else:
                txt = self._lim(str(self.value))

            return f"{txt:{self.params['align']}{self.width}}"

        def _lim(self, txt):
            if len(txt) > self.width:
                lng = self.width - len(self.params["ellipse"])
                txt = f"{self.params['ellipse']}{txt[-lng:]}"
            return txt

        @property
        def width(self):
            return self.params["width"]

        @width.setter
        def width(self, value):
            self.params["width"] = value

        @property
        def dtype(self):
            return self.params["dtype"]

        @property
        def vsize(self):
            """return the length of the value as a string"""
            if isinstance(self.value, str):
                return len(self.value)
            elif isinstance(self.value, (int, float)):
                return len(f"{self.value:{self.dtype}}")
            else:
                return len(str(self.value))

        def set_params(self, params):
            for k, v in params.items():
                if k in self.params.keys():
                    self.params[k] = v

    def __init__(
        self,
        header_lines,
        minwidth=1,
        maxwidth=50,
        col_sep=" ",
        dtype="g",
        align="^",
        flag="#",
        ellipse="..",
        fpreci="",
        lmargin="",
    ):
        if not isinstance(header_lines, (list, tuple)):
            raise ValueError("header_lines must be a 2D list")

        dim = None
        for line in header_lines:

            if not isinstance(line, (list, tuple)):
                raise ValueError("header_lines must be a 2D list")

            if dim is None:
                dim = len(line)
            elif len(line) != dim:
                raise ValueError("header_lines: all lists must have the same size")

        if align not in ["^", "<", ">"]:
            raise ValueError("align must be in ['^', '<', '>'] ")

        self.col_sep = col_sep
        self.minwidth = minwidth
        self.maxwidth = max(maxwidth, self.minwidth)

        self.default_params = {
            "dtype": dtype,
            "align": align,
            "width": minwidth,
            "flag": flag,  # '' or '#'
            "ellipse": ellipse,
            "fpreci": fpreci,  # '' or '.3' for example
        }

        self.lmargin = lmargin
        self.col_num = 0
        self._cells = []  # [raw][col]

        for values in header_lines:
            self.add_line(values)

        self.resize()

    @property
    def full_width(self):
        if self._cells:
            full_width = sum([c.width for c in self._cells[0]])
            full_width += len(self.col_sep) * (self.col_num - 1)
            return full_width

    def get_line(self, index):
        return self._cells[index]

    def get_column(self, index):
        return list(zip(*self._cells))[index]

    def get_col_params(self, index):
        """get current column width, based on the cells of the last line"""

        if self._cells:
            return self._cells[-1][index].params
        else:
            return self.default_params

    def set_column_params(self, index, params):
        for cell in self.get_column(index):
            cell.set_params(params)

    def add_line(self, values, line_index=None):
        dim = len(values)
        if self._cells:
            if dim != self.col_num:
                raise ValueError(
                    f"cannot add a line with a different number of columns: {dim} != {self.col_num}"
                )
        else:
            self.col_num = dim

        line = [self._Cell(v, **self.get_col_params(i)) for i, v in enumerate(values)]

        if line_index is None:
            self._cells.append(line)
        else:
            self._cells.insert(line_index, line)

        return self.lmargin + self.col_sep.join([str(cell) for cell in line])

    def add_separator(self, sep="", line_index=None):
        if self._cells:
            self.add_line([sep * c.width for c in self._cells[0]], line_index)

    def resize(self, minwidth=None, maxwidth=None):
        if minwidth:
            self.minwidth = minwidth
        if maxwidth:
            self.maxwidth = max(maxwidth, self.minwidth)

        for col in zip(*self._cells):
            self._find_best_width(col)

    def _find_best_width(self, col_cells):

        _maxwidth = max([c.vsize for c in col_cells])
        _maxwidth = max(_maxwidth, self.minwidth)

        if self.maxwidth:
            _maxwidth = min(_maxwidth, self.maxwidth)

        for c in col_cells:
            c.width = _maxwidth

    def __str__(self):
        lines = [
            self.lmargin + self.col_sep.join([str(cell) for cell in line_cells])
            for line_cells in self._cells
        ]
        return "\n".join(lines)
