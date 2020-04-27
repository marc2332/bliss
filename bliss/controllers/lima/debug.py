from bliss.common.utils import autocomplete_property


class LimaDebug:
    def __init__(self, name, proxy):
        self.name = f"{name}_debug"
        self.__name = name
        self.__proxy = proxy
        self.__module = None
        self.__debtype = None

    def __info__(self):
        info = f"[{self.__name}] server debug state :\n"
        info += "Debug Modules :\n"
        info += self.modules.__info__()
        info += "Debug Types :\n"
        info += self.types.__info__()
        return info

    def on(self):
        self.modules.on()
        self.types.on()

    def off(self):
        self.modules.off()
        self.types.off()

    @autocomplete_property
    def modules(self):
        if self.__module is None:
            try:
                self.__module = LimaDebugItem(
                    self.__proxy,
                    "debug_modules",
                    "debug_modules_possible",
                    {"none": True},
                )
            except AttributeError:
                raise RuntimeError("Failed to access server debug modules attributes")
        return self.__module

    @autocomplete_property
    def types(self):
        if self.__debtype is None:
            try:
                self.__debtype = LimaDebugItem(
                    self.__proxy, "debug_types", "debug_types_possible", {"fatal": True}
                )
            except AttributeError:
                raise RuntimeError("Failed to access server debug types attributes")
        return self.__debtype


class LimaDebugItem:
    def __init__(self, proxy, attr_value, attr_list, off_state):
        self.__proxy = proxy
        self.__attr_value = attr_value
        self.__off_state = off_state
        self.__values = dict([(m.lower(), m) for m in getattr(self.__proxy, attr_list)])

    def __get(self):
        curr = getattr(self.__proxy, self.__attr_value)
        values = dict()
        for (name, val) in self.__values.items():
            values[name] = val in curr
        return values

    def __set(self, vals_dict):
        vals = [self.__values[name] for (name, val) in vals_dict.items() if val is True]
        setattr(self.__proxy, self.__attr_value, vals)

    def __set_all(self):
        setattr(self.__proxy, self.__attr_value, list(self.__values.values()))

    def __check(self, values):
        vals = [val.lower() for val in values]
        errs = [val for val in vals if val not in self.__values]
        if len(errs):
            raise ValueError(f"Invalid lima debug values {errs}")
        return vals

    def __info__(self):
        info = ""
        mods = self.__get()
        for (mod, val) in mods.items():
            if mod != "none":
                name = self.__values[mod]
                state = val is True and "ON" or "OFF"
                info += f"    {name:15.15} : {state}\n"
        return info

    def set(self, *values):
        if not len(values):
            self.__set(self.__off_state)
        else:
            ask_vals = self.__check(values)
            vals = dict([(name, False) for name in self.__values.keys()])
            for val in ask_vals:
                vals[val] = True
            self.__set(vals)

    def on(self, *values):
        if not len(values):
            self.__set_all()
        else:
            ask_vals = self.__check(values)
            vals = self.__get()
            for val in ask_vals:
                vals[val] = True
            self.__set(vals)

    def off(self, *values):
        if not len(values):
            self.__set(self.__off_state)
        else:
            ask_vals = self.__check(values)
            vals = self.__get()
            for val in ask_vals:
                vals[val] = False
            self.__set(vals)
