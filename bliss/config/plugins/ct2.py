import os

from jinja2 import Environment, FileSystemLoader

from .default import create_objects_from_config_node


__KNOWN_PARAMS = "address"

__this_path = os.path.dirname(os.path.realpath(__file__))


def get_jinja2():
    global __environment
    try:
        return __environment
    except NameError:
        __environment = Environment(loader=FileSystemLoader(__this_path))
    return __environment


def get_html(cfg):
    klass = cfg.get("class", "P201")
    
    params = (
        dict(name="address", label="Address", value=cfg['address'],),
        dict(name="clock", label="Clock", value=cfg['clock'],),
    )
    
    filename = "{0}.html".format(klass)
    html_template = get_jinja2().select_template([filename, "ct2.html"])
    
    return html_template.render(params=params, counters=cfg.get("counters"),
                                channels=cfg.get("channels"))
