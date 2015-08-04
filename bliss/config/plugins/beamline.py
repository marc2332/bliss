from __future__ import absolute_import
import os
import sys

import flask.json

from jinja2 import Environment, FileSystemLoader

__this_path = os.path.realpath(os.path.dirname(__file__))


def get_jinja2():
    global __environment
    try:
        return __environment
    except NameError:
        __environment = Environment(loader=FileSystemLoader(__this_path))
    return __environment


def get_main(cfg):
   template = get_jinja2().select_template(("beamline.html",))   

   params = {}
   for k, v in cfg.root.iteritems():
     if not isinstance(v, (list, tuple, dict)):
       params[k] = v

   html = template.render(dict(params=params))

   return flask.json.dumps(dict(html=html))    


def edit(cfg, request):
    if request.method == "POST":
        for k, v in request.form.items():
            cfg.root[k] = v
    cfg.root.save()
    
    return flask.json.dumps(dict(message="configuration applied!", 
                                 type="success"))
