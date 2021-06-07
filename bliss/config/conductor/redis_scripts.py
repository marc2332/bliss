"""Utilities for Redis server-side scripts
"""

_SCRIPTS = dict()


def register_script(redisproxy, script_name: str, script: str) -> None:
    """Local registration. The registration with the Redis server is
    done on first usage.
    """
    if script_name in _SCRIPTS:
        return
    scriptobj = redisproxy.register_script(script)
    scriptobj.registered_client = None
    # scriptobj only contains the script hash and code
    _SCRIPTS[script_name] = scriptobj


def evaluate_script(redisproxy, script_name: str, keys=tuple(), args=tuple()):
    """Evaluate a server-side Redis script
    """
    if script_name not in _SCRIPTS:
        raise RuntimeError(f"Redis script {repr(script_name)} is not registered")
    scriptobj = _SCRIPTS[script_name]
    return scriptobj(keys=keys, args=args, client=redisproxy)
