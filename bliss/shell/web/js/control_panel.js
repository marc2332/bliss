function ControlPanel(div_id, session_id) {
    this.motors = {};
    this.actuators = {};
    this.shutters = {};
    this.session_id = session_id;

    this.refresh_btn = $("<button style='width:100%;'>Refresh</button>").button();
    this.refresh_btn = $("<button>Refresh</button>");
    this.refresh_btn.css("width", "100%");
    this.refresh_btn.button().css("font-size", "0.8em");
    this.counters_div = $('<div style="width:100%;"></div>');
    this.counters_div.append($('<span class="control-panel-header">Counters</span>'));
    this.counters_list = $("<ul class='items-list'></ul>");
    this.counters_div.append(this.counters_list);
    this.motors_div = $('<div style="width:100%;"></div>');
    this.motors_div.append($('<span class="control-panel-header">Motors</span>'));
    this.actuators_div = $('<div style="width:100%;"></div>');
    this.actuators_div.append($('<span class="control-panel-header">Actuators</span>'));
    this.shutters_div = $('<div style="width:100%;"></div>');
    this.shutters_div.append($('<span class="control-panel-header">Shutters</span>'));
    this.motors_list = $('<ul class="items-list"></ul>');
    this.motors_div.append(this.motors_list);
    this.actuators_list = $('<ul class="items-list"></ul>');
    this.actuators_div.append(this.actuators_list);
    this.shutters_list = $('<ul class="items-list"></ul>');
    this.shutters_div.append(this.shutters_list);
    $("#" + div_id).append(this.refresh_btn);
    $("#" + div_id).append(this.counters_div);
    $('#' + div_id).append(this.motors_div);
    $('#' + div_id).append(this.actuators_div);
    $('#' + div_id).append(this.shutters_div);

    this.refresh_btn.click($.proxy(this.refresh, this));

    /* 
       connect to control panel events stream 
    */
    this.output_stream = new EventSource(this.session_id + '/control_panel_events');
    this.output_stream.onmessage = $.proxy(function(e) {
        if (e.data) {
            var output = JSON.parse(e.data);
            this.update_display(output.data);
        }
    }, this);

    /*
       get objects, and populate lists
    */
    this.get_objects();
};

ControlPanel.prototype = {
    refresh: function() {
        this.counters_list.empty();
        this.motors_list.empty();
        this.actuators_list.empty();
        this.shutters_list.empty();
        this.motors = {};
        this.actuators = {};
        this.shutters = {};

        this.get_objects();
    },

    get_objects: function() {
        $.ajax({
            error: function(XMLHttpRequest, textStatus, errorThrown) {
                alert(textStatus);
            },
            url: this.session_id + '/objects',
            type: 'GET',
            dataType: 'json',
            success: $.proxy(function(res) {
                var counters = res.counters;
                for (var i = 0; i<counters.length; i++) {
                   var name = counters[i].name;
                   var dom_item = $("<li></li>");
                   dom_item.addClass("control-panel-item");
                   this.counters_list.append(dom_item);               
                }
 
                var motors = res.motors;
                for (var i = 0; i < motors.length; i++) {
                    var name = motors[i].name;
                    var pos = motors[i].position;
                    var state = motors[i].state;
                    var dom_item = $("<li></li>");
                    dom_item.addClass("control-panel-item");
                    this.motors_list.append(dom_item);
                    this.motors[name] = {
                        name: name,
                        dom_item: dom_item,
                        state: state,
                        position: pos
                    }
                    this.update_motor(this.motors[name]);
                }

                var inout = res.inout;
                for (var i = 0; i < inout.length; i++) {
                    var name = inout[i].name;
                    var state = inout[i].state;
                    this.actuators[name] = {
                        name: name,
                        state: state
                    }
                    var dom_item = this.add_item_with_buttons(this.actuators, name, "In", "set_in", "Out", "set_out");
                    this.actuators_list.append(dom_item);
                    this.update_inout(this.actuators[name]);
                }

                var shutters = res.openclose;
                for (var i = 0; i < shutters.length; i++) {
                    var name = shutters[i].name;
                    var state = shutters[i].state;
                    this.shutters[name] = {
                        name: name,
                        state: state
                    }
                    var dom_item = this.add_item_with_buttons(this.shutters, name, "Open", "open", "Close", "close");
                    this.shutters_list.append(dom_item);
                    this.update_inout(this.actuators[name]);
                }
            }, this)
        });
    },

    add_item_with_buttons: function(obj_dict, name, label1, cmd1, label2, cmd2) {
        var dom_item = $("<li></li>");
        dom_item.addClass("control-panel-item");
        var in_button = $("<span>&nbsp;" + label1 + "&nbsp;</span>");
        in_button.addClass("control-panel-toggle");
        var out_button = in_button.clone();
        out_button.html("&nbsp;Out&nbsp;");
        in_button.click(function() {
            $.get(this.session_id + "/control_panel/run/" + name + "/" + cmd1);
        });
        out_button.click(function() {
            $.get(this.session_id + "/control_panel/run/" + name + "/" + cmd2);
        });
        dom_item.html(name + "&nbsp;");
        dom_item.append(out_button);
        dom_item.append(in_button);
        var obj = obj_dict[name];
        obj.dom_item = dom_item;
        obj.in_button = in_button;
        obj.out_button = out_button;
        return (dom_item);
    },

    update_motor: function(motor) {
        var name = motor.name;
        var state = motor.state;
        var pos = motor.position;
        var dom_item = motor.dom_item;

        if (pos != undefined) {
            dom_item.html(name + "&nbsp;" + pos);
        }
        dom_item.removeClass("control-panel-item-ready control-panel-item-moving control-panel-item-fault control-panel-item-home control-panel-item-onlimit");
        if (state == "READY") {
            dom_item.addClass("control-panel-item-ready");
        } else if (state == "MOVING") {
            dom_item.addClass("control-panel-item-moving");
        } else if (state == "FAULT") {
            dom_item.addClass("control-panel-item-fault");
        } else if (state == "ONLIMIT") {
            dom_item.addClass("control-panel-item-onlimit");
        } else if (state == "HOME") {
            dom_item.addClass("control-panel-item-home");
        }
    },

    update_inout: function(actuator) {
        var state = actuator.state;
        var in_button = actuator.in_button;
        var out_button = actuator.out_button;
        in_button.removeClass("control-panel-toggle-pressed");
        out_button.removeClass("control-panel-toggle-pressed");

        if (state == "IN") {
            in_button.addClass("control-panel-toggle-pressed");
        } else if (state == "OUT") {
            out_button.addClass("control-panel-toggle-pressed");
        }
    },

    update_shutter: function(shutter) {
        var state = shutter.state;
        var open_button = shutter.in_button;
        var close_button = shutter.out_button;
        in_button.removeClass("control-panel-toggle-pressed");
        out_button.removeClass("control-panel-toggle-pressed");

        if (state == "OPENED") {
            in_button.addClass("control-panel-toggle-pressed");
        } else if (state == "CLOSED") {
            out_button.addClass("control-panel-toggle-pressed");
        }
    },

    update_display: function(data) {
        var lists = [this.motors, this.actuators, this.shutters];
        var update_funcs = [this.update_motor, this.update_inout, this.update_shutter];

        for (var i = 0; i < lists.length; i++) {
            var obj = lists[i][data.name];
            if (obj) {
                $.extend(obj, data);
                update_funcs[i](obj);
                break;
            }
        }
    }
};
