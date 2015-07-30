from __future__ import absolute_import

import os
import shlex

import flask.json

from jinja2 import Environment, FileSystemLoader

from .default import create_objects_from_config_node

__this_path = os.path.dirname(os.path.realpath(__file__))

import ct2

GENERAL_PARAMS_SEQ = (
#      name                          type    writable   default value         label                     group         description
    ("name",                      ('unicode', True,  None,                  "Name",                     None,        "card name")),
    ("class",                     ('str',     True,  None,                  "Type",                     None,        "card type")),
    ("address",                   ('str',     True,  None,                  "Address",                  None,        "card address (ex: /dev/p201)")),
    ("clock",                     ('Clock',   True,  ct2.Clock.CLK_100_MHz, "Clock",                    None,        "card clock")),
    ("dma interrupt",             ('bool',    True,  False,                 "DMA interrupt",            "interrupt", "End of DMA transfer will trigger interrupt")),
    ("fifo half full interrupt",  ('bool',    True,  False,                 "FIFO half full interrupt", "interrupt", "FIFO half full will trigger interrupt")),
    ("error interrupt",           ('bool',    True,  False,                 "Error interrupt",          "interrupt", "FIFO transfer error or too close DMA triggers will trigger interrupt")),
)

GENERAL_PARAMS_DICT = {}
for k, v in GENERAL_PARAMS_SEQ:
    GENERAL_PARAMS_DICT[k] = dict(name=k, type=v[0], access=v[1], default=v[2],
                                  label=v[3], group=v[4], description=v[5])

COUNTER_PARAMS_SEQ = (
#      name             type            writable      default value           label         group       description
    ("address",         ('int',            False, None,                        "#",      None,        "counter ID")),
#    ("name",            ('unicode',        True,  "",                          "Name",         None,        "counter name")),
    ("clock source",    ('CtClockSrc',     True,  ct2.CtClockSrc.CLK_1_25_KHz, "Clock",        "source",    "counter clock source")),
    ("gate source",     ('CtGateSrc',      True,  ct2.CtGateSrc.GATE_CMPT,     "Gate",         "source",    "counter gate source")),
    ("start source",    ('CtHardStartSrc', True,  ct2.CtHardStartSrc.SOFTWARE, "Start",        "source",    "hardware start source")),
    ("stop source",     ('CtHardStopSrc',  True,  ct2.CtHardStopSrc.SOFTWARE,  "Stop",         "source",    "hardware stop source")),
    ("latch sources",   ('list<int>',      True,  [],                          "Latch(es)",    "source",    "counter to latch(es) on counter signals hardware stop, software stop and software disable (comma separated)")),
    ("reset",           ('bool',           True,  False,                       "Reset",        None,        "reset from hardware or software stop")),
    ("stop",            ('bool',           True,  False,                       "Stop",         None,        "stop from hardware stop")),
    ("interrupt",       ('bool',           True,  False,                       "Interrupt",    "interrupt", "counter N stop triggers interrupt")),
    ("software enable", ('bool',           True,  False,                       "Soft. enable", None,        "software enable/disable")),
    ("comparator",      ('int',            True,  0,                           "Comp.",   None,        "counter N comparator value")),
)

COUNTER_PARAMS_DICT = {}
for k, v in COUNTER_PARAMS_SEQ:
    COUNTER_PARAMS_DICT[k] = dict(name=k, type=v[0], access=v[1], default=v[2],
                                  label=v[3], group=v[4], description=v[5])

IN_CHANNEL_PARAMS_SEQ = (
#      name             type            writable      default value           label         group       description
    ("address",         ('int',          False, None,                        "#",        None,     "channel ID")),
#    ("name",            ('unicode',      True,  "",                          "Name",           None,     "channel name")),
    ("level",           ('Level',        True,  ct2.Level.DISABLE,           "Level",          None,     "channel level (TTL, NIM, Both or None)")),
    ("50 ohm",          ('bool',         True,  False,                       "50 &#8486;",     None,     "50 &#8486; adapter")),
    ("readback",        ('bool',         True,  False,                       "Readback",       None,     "readback")),
    ("interrupt",       ('list<str>',    True,  [],                          "Edge interrupt", None,     "edge interrupt: rising, falling or both (comma separated)")),
)

IN_CHANNEL_PARAMS_DICT = {}
for k, v in IN_CHANNEL_PARAMS_SEQ:
    IN_CHANNEL_PARAMS_DICT[k] = dict(name=k, type=v[0], access=v[1], default=v[2],
                                  label=v[3], group=v[4], description=v[5])

OUT_CHANNEL_PARAMS_SEQ = (
#      name             type            writable      default value           label         group       description
    ("address",         ('int',          False, None,                        "#",        None,     "channel ID")),
#    ("name",            ('unicode',      True,  "",                          "Name",           None,     "channel name")),
    ("software level",  ('bool',         True,  False,                      "Sw. enable",      None,     "software enable")),
    ("level",           ('bool',         True,  False,                      "Level",           None,     "level")),
    ("source",          ('OutputSrc',    True,  ct2.OutputSrc.SOFTWARE,     "Source",          "source", "output source")),
    ("filter enable",   ('bool',         True,  False,                      "Filter enable",   "filter", "output filter enable/disable")),
    ("filter clock",    ('FilterClock',  True,  ct2.FilterClock.CLK_100_MHz,"Filter clock",    "filter", "output filter clock")),
    ("filter polarity", ('bool',         True,  False,                      "Filter polarity", "filter", "output filter polarity (0 or 1)")),
)

OUT_CHANNEL_PARAMS_DICT = {}
for k, v in OUT_CHANNEL_PARAMS_SEQ:
    OUT_CHANNEL_PARAMS_DICT[k] = dict(name=k, type=v[0], access=v[1], default=v[2],
                                  label=v[3], group=v[4], description=v[5])

def get_jinja2():
    global __environment
    try:
        return __environment
    except NameError:
        __environment = Environment(loader=FileSystemLoader(__this_path))
    return __environment

def get_tree(cfg):
    klass =  cfg.get("class")
    if klass is None:
        result = dict(type="ct/ch",
                      path=os.path.join(get_tree(cfg.parent)['path'], cfg['name']),
                      icon="fa fa-square")
    else:
        result = dict(type="Counter card",
                      path=os.path.join(cfg.filename, cfg["name"]),
                      icon="fa fa-credit-card")
    return result

def get_html(cfg):
    klass = cfg.get("class")
    if klass is None:
        return get_channel_html(cfg)
    else:
        return get_card_html(cfg)

def get_channel_html(cfg):
    return "<h1>TODO</h1>"

def get_card_html(cfg):
    cfg = dict(cfg.items())
    card_type = cfg.get("class")
    card = getattr(ct2, card_type)
    cts = cfg.setdefault("counters", [])
    counters = dict([(i, dict(address=i)) for i in card.COUNTERS])
    for ct in cts:
        counters[ct["address"]] = ct
    channels = cfg.setdefault("channels", [])
    in_channels = dict([(i, dict(address=i)) for i in card.INPUT_CHANNELS])
    out_channels = dict([(i, dict(address=i)) for i in card.OUTPUT_CHANNELS])
    for ch in channels:
        addr = ch['address']
        if addr in in_channels:
            ch['input']["address"] = addr
            in_channels[addr] = ch['input']
        if addr in out_channels:
            ch['output']["address"] = addr
            out_channels[addr] = ch['output']

    general_params = dict([(k, cfg[k]) for k in GENERAL_PARAMS_DICT if k in cfg])

    params = dict(
        ct2=ct2,
        GENERAL_PARAMS_SEQ=GENERAL_PARAMS_SEQ,
        COUNTER_PARAMS_SEQ=COUNTER_PARAMS_SEQ,
        IN_CHANNEL_PARAMS_SEQ=IN_CHANNEL_PARAMS_SEQ,
        OUT_CHANNEL_PARAMS_SEQ=OUT_CHANNEL_PARAMS_SEQ,
        params=general_params,
        counters=counters,
        in_channels=in_channels,
        out_channels=out_channels)
    filename = "{0}.html".format(card_type)
    html_template = get_jinja2().select_template([filename, "ct2.html"])
    return html_template.render(**params)


def __value_to_config(value, dictio):
    if value is None:
        value = dictio['default']
    if value is None:
        return
    type_str = dictio['type']
    if type_str == 'list<int>':
        try:
            return map(int, value.split(","))
        except:
            return ()
    elif type_str == 'list<str>':
        try:
            ret = shlex.shlex(value)
            ret.whitespace += ","
            return list(ret)
        except:
            return ()
    elif type_str == 'bool':
        if value in ('on', 'true'):
            value = True
        elif value in ('off', 'false'):
            value = False
        return bool(value)
    elif type_str == 'int':
        return int(value)
    elif type_str == 'float':
        return float(value)
    elif type_str == 'str':
        return str(value)
    elif type_str == 'unicode':
        return unicode(value)
    else:
        if not isinstance(value, ct2.enum.Enum):
            value = getattr(ct2, type_str)[value]
        return value.name
    return value


def __get_label_from_enum(en_value):
    pass


def __get_enum_from_label(label, en):
    pass


def empty_counter(addr):
    return dict(address=addr)


def empty_channel(addr):
    return dict(address=addr, input=dict(), output=dict())


def card_edit(cfg, request):
    if request.method == "POST":
        form = dict([(k,v) for k,v in request.form.items()])
        orig_card_name = form.pop("__original_name__")
        card_name = form["name"]
        card_type = form.get("class")
        card = getattr(ct2, card_type)
        result = dict(name=card_name)
        if card_name != orig_card_name:
            result["message"] = "Change of card name not supported yet!"
            result["type"] = "danger"
            return flask.json.dumps(result)
        card_cfg = cfg.get_config(orig_card_name)

        cfg, counters, channels = {}, {}, {}
        # handle generic card parameters
        for p_name, p_info in GENERAL_PARAMS_DICT.items():
            cfg[p_name] = __value_to_config(form.get(p_name), p_info)

        # handle counter parameters
        for p_name, p_info in COUNTER_PARAMS_DICT.items():
            if p_name == "address": continue
            for counter in card.COUNTERS:
                ct = counters.setdefault(counter, empty_counter(counter))
                ct_p_name = "ct {0} {1}".format(counter, p_name)
                ct[p_name] = __value_to_config(form.get(ct_p_name), p_info)

        # handle input channels parameters
        for p_name, p_info in IN_CHANNEL_PARAMS_DICT.items():
            if p_name == "address": continue
            for channel in card.INPUT_CHANNELS:
                ch = channels.setdefault(channel, empty_channel(channel))['input']
                ch_p_name = "inch {0} {1}".format(channel, p_name)
                ch[p_name] = __value_to_config(form.get(ch_p_name), p_info)

        # handle output channels parameters
        for p_name, p_info in OUT_CHANNEL_PARAMS_DICT.items():
            if p_name == "address": continue
            for channel in card.OUTPUT_CHANNELS:
                ch = channels.setdefault(channel, empty_channel(channel))['output']
                ch_p_name = "outch {0} {1}".format(channel, p_name)
                ch[p_name] = __value_to_config(form.get(ch_p_name), p_info)

        cfg['counters'] = [counters[ct] for ct in sorted(counters)]
        cfg['channels'] = [channels[ch] for ch in sorted(channels)]

        card_cfg.update((k, v) for k, v in cfg.items())
        card_cfg.save()

        result["message"] = "'%s' configuration applied!" % card_name
        result["type"] = "success"

        return flask.json.dumps(result)
