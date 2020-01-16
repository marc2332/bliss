from bliss.common.counter import CalcCounter
from bliss.controllers.counter import CalcCounterController
import numexpr


class ExpressionCalcCounter(CalcCounter):
    def __init__(self, name, config):

        self._expression = config["expression"]
        self._constants = config.get("constants").to_dict()
        calc_ctrl_config = {
            "inputs": config["inputs"],
            "outputs": [{"name": name, "tags": name}],
        }
        self.__controller = CalcCounterController(name + "_ctrl", calc_ctrl_config)

        def _calc_function(input_dict):
            exp_dict = self._constants.copy()
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
        self._constants = config.get("constants").to_dict()

        self._expressions = dict()
        for o in config["outputs"]:
            self._expressions[o["name"]] = o["expression"]

        super().__init__(name, config)

        def _calc_function(input_dict):
            exp_dict = self._constants.copy()
            for cnt in self.inputs:
                exp_dict.update({self.tags[cnt.name]: input_dict[self.tags[cnt.name]]})
            return {
                self.tags[out]: numexpr.evaluate(
                    expression, global_dict={}, local_dict=exp_dict
                )
                for out, expression in self._expressions.items()
            }

        self.calc_function = _calc_function
