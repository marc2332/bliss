function ControlPanel(div_id, session_id) {
    this.motors = {};
    this.actuators = {};
    this.session_id = session_id;

    this.refresh_btn = $("<button style='width:100%;'>Refresh</button>").button();
    this.refresh_btn = $("<button>Refresh</button>");
    this.refresh_btn.css("width", "100%");
    this.refresh_btn.button().css("font-size", "0.8em");
    this.motors_div = $('<div style="width:100%;"></div>');
    this.motors_div.append($('<span class="control-panel-header">Motors</span>'));
    this.actuators_div = $('<div style="width:100%;"></div>');
    this.actuators_div.append($('<span class="control-panel-header">Actuators</span>'));
    this.motors_list = $('<ul class="items-list"></ul>');
    this.motors_div.append(this.motors_list);
    this.actuators_list = $('<ul class="items-list"></ul>');
    this.actuators_div.append(this.actuators_list);
    $("#" + div_id).append(this.refresh_btn);
    $('#' + div_id).append(this.motors_div);
    $('#' + div_id).append(this.actuators_div);

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
        this.motors_list.empty();
        this.actuators_list.empty();
        this.motors = {};
        this.actuators = {};

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
                    };
                    this.update_motor(this.motors[name]);
                };

                var inout = res.inout;
                for (var i = 0; i < inout.length; i++) {
                    var session_id = this.session_id;
                    var name = inout[i].name;
                    var state = inout[i].state;
                    var dom_item = $("<li></li>");
                    dom_item.addClass("control-panel-item");
                    var in_button = $("<span>&nbsp;In&nbsp;</span>");
                    in_button.addClass("control-panel-toggle");
                    var out_button = in_button.clone();
                    out_button.html("&nbsp;Out&nbsp;");
                    in_button.click(function() {
                        $.ajax({
                            url: session_id + "/control_panel/run/" + name + "/set_in",
                            type: 'GET',
                            dataType: 'json'
                        });
                    });
                    out_button.click(function() {
                        $.ajax({
                            url: session_id + "/control_panel/run/" + name + "/set_out",
                            type: 'GET',
                            dataType: 'json'
                        });
                    });
                    dom_item.html(name + "&nbsp;");
                    dom_item.append(out_button);
                    dom_item.append(in_button);
                    this.actuators_list.append(dom_item);
                    this.actuators[name] = {
                        name: name,
                        dom_item: dom_item,
                        in_button: in_button,
                        out_button: out_button,
                        state: state
                    };
                    this.update_inout(this.actuators[name]);
                };
            }, this)
        });
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
    update_display: function(data) {
        var lists = [this.motors, this.actuators];
        var update_funcs = [this.update_motor, this.update_inout];

        for (var i = 0; i < lists.length; i++) {
            var obj = lists[i][data.name];
            if (obj) {
                $.extend(obj, data);
                update_funcs[i](obj);
                break;
            }
        }
    },
};