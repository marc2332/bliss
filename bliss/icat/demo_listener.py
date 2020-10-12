from pprint import pprint
from bliss.data.node import get_node


def demo_listener(session_name):
    n = get_node(session_name)
    for dataset in n.walk(wait=False, filter="dataset"):
        if dataset.is_closed:
            print(f"dataset {dataset.db_name} is closed the collected metadata is:")
            pprint(dataset.metadata)
        else:
            print(f"dataset {dataset.db_name} is not yet closed")
