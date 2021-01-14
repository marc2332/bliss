import os


__this_file = os.path.realpath(__file__)
__this_path = os.path.dirname(__this_file)


def get_resource(resource):
    """Returns the root to go to a web resource"""
    return os.path.join(__this_path, resource)
