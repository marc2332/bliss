import os

def get_redis_config_path():
    base_path,_ = os.path.split(__file__)
    return os.path.join(base_path,'redis.conf')
