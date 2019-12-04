from bliss import global_map


def __find_wagos():
    """retrieves all Wagos from the map"""
    try:
        wagos = tuple(
            global_map[id_]["instance"]() for id_ in global_map.find_children("wago")
        )
    except TypeError:
        return ()
    else:
        return wagos


def interlock_state(*instances):
    """Returns the state of interlocks:
    Made for Wagos, but intended to be used in future for other
    kind of interlocks

    Args: any number of interlock instances, if no one is given
          it will be shown for any known instance

    Returns:
        Type of answers:
          For Wagos we can have 4 different states:
           - tripped (True means that the relay is tripped)
           - alarm (True means alarm is present)
           - cfgerr (True means that there is a configuration error)
           - hdwerr (True means that there is an hardware error)
    """
    from bliss.controllers.wago.interlocks import interlock_state as _interlock_state
    from bliss.controllers.wago.wago import MissingFirmware

    wagos = __find_wagos()

    if not len(instances):
        instances = ()
        instances += __find_wagos()
        # eventual others intances

    states = {}

    for instance in instances:
        if instance in wagos:
            try:
                states[instance.name] = _interlock_state(instance.controller)
            except MissingFirmware:
                continue
    return states
