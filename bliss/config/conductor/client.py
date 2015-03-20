from . import connection

_default_connection = None


def check_connection(func):
    def f(*args,**keys):
        global _default_connection
        conn = keys.get("connection", _default_connection)
        if conn is None and _default_connection is None:
            _default_connection = connection.Connection()
            conn = _default_connection
	keys["connection"]=conn
        return func(*args,**keys)
    return f


@check_connection
def lock(*devices,**params):
    devices_name = [d.name for d in devices]
    params["connection"].lock(devices_name,**params)


@check_connection
def unlock(*devices,**params):
    devices_name = [d.name for d in devices]
    params["connection"].unlock(devices_name,**params)


@check_connection
def get_cache_address(connection=None):
    return connection.get_redis_connection_address()


@check_connection
def get_cache(db=0, connection=None):
    return connection.get_redis_connection(db=db)


@check_connection
def get_config_file(file_path, connection=None) :
    return connection.get_config_file(file_path)


@check_connection
def get_config_db_files(base_path='',timeout=3., connection=None):
    path2files = connection.get_config_db(base_path=base_path,timeout=timeout)
    return path2files

@check_connection
def set_config_db_file(filepath,content,timeout=3.,connection = None):
    connection.set_config_db_file(filepath,content,timeout=timeout)
