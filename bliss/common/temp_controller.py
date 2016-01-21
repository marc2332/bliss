class TInput:
    def __init__(self, config):
        pass

class TOutput:
    def __init__(self, config):
        pass

class TCtrlLoop:
    def __init__(self, config):
        pass

class TController:
    def __init__(self, config, inputs, outputs, loops):
        self._objects = dict()

        for name, input_cfg in inputs:
            self._objects[name] = TInput(input_cfg)
        for name, input_cfg in outputs:
            self._objects[name] = TOutput(input_cfg)
        for name, input_cfg in loops:
            self._objects[name] = TCtrlLoop(input_cfg)

    def get_object(self, name):
        return self._objects.get(name)
        

    
