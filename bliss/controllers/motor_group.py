try:
    from bliss.controllers.motor_group import Group
except ImportError:
    class Group:
        pass

