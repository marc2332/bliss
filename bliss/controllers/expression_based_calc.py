from bliss.common.counter import CalcCounter
from bliss.controllers.counter import CalcCounterController
from bliss.config.beacon_object import BeaconObject
from bliss.config.static import ConfigReference
import numexpr


class ExprCalcParameters(BeaconObject):
    def __new__(cls, name, config):
        cls = type(cls.__name__, (cls,), {})
        if "constants" in config:
            for key, value in (
                config["constants"].to_dict(resolve_references=False).items()
            ):
                if isinstance(value, str) and value.startswith("$"):
                    # this constant is a reference
                    setattr(cls, key, config["constants"].raw_get(key))
                else:
                    setattr(cls, key, BeaconObject.property_setting(key, default=value))
        return object.__new__(cls)

    def __init__(self, name, config):
        super().__init__(config, name=name, share_hardware=False, path=["constants"])

    def to_dict(self):
        ret = {}
        for key in self.config.keys():
            v = getattr(self, key)
            if isinstance(v, ConfigReference):
                v = v.dereference()
            ret[key] = v
        return ret

    def __info__(self):
        # TODO: make nicer!
        return str(self.to_dict())


class ExpressionCalcCounter(CalcCounter):
    def __init__(self, name, config):
        self._expression = config["expression"]

        self.constants = ExprCalcParameters(name, config)

        calc_ctrl_config = {
            "inputs": config["inputs"],
            "outputs": [{"name": name, "tags": name}],
        }
        self.__controller = CalcCounterController(name + "_ctrl", calc_ctrl_config)

        def _calc_function(input_dict):
            exp_dict = self.constants.to_dict()
            for cnt in self.__controller.inputs:
                exp_dict.update(
                    {
                        self.__controller.tags[cnt.name]: input_dict[
                            self.__controller.tags[cnt.name]
                        ]
                    }
                )
            return {
                self.__controller.tags[
                    self.__controller.outputs[0].name
                ]: numexpr.evaluate(
                    self._expression, global_dict={}, local_dict=exp_dict
                )
            }

        self.__controller.calc_function = _calc_function

        super().__init__(name, self.__controller)


class ExpressionCalcCounterController(CalcCounterController):
    def __init__(self, name, config):
        self.constants = ExprCalcParameters(name, config)
        self._expressions = dict()

        for o in config["outputs"]:
            self._expressions[o["name"]] = o["expression"]

        super().__init__(name, config)

        def _calc_function(input_dict):
            exp_dict = self.constants.to_dict()
            for cnt in self.inputs:
                exp_dict.update({self.tags[cnt.name]: input_dict[self.tags[cnt.name]]})
            return {
                self.tags[out]: numexpr.evaluate(
                    expression, global_dict={}, local_dict=exp_dict
                )
                for out, expression in self._expressions.items()
            }

        self.calc_function = _calc_function
