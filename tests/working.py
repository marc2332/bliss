import pprint


class SomeClass(object):
    def __init__(self, name, config):
        print("SomeOutput")


class SomeClass2(object):
    def __init__(self, name, config):
        raise RuntimeError
