function ControlPanel(div_id, session_id) {
    this.motors = {};
    this.session_id = session_id;

    this.motors_div = $('<div style="width:100%;"></div>');
    this.motors_div.append($('<span class="control-panel-header">Motors</span>'));
    this.motors_list = $('<ul class="items-list"></ul>');
    this.motors_div.append(this.motors_list);
    $('#' + div_id).append(this.motors_div);

    /* 
       connect to control panel events stream 
    */
    this.output_stream = new EventSource('control_panel_events/' + this.session_id);
    this.output_stream.onmessage = $.proxy(function(e) {
        if (e.data) {
            var output = JSON.parse(e.data);
            this.update_display(output.data);
        }
    }, this);

    /*
       get motors names, and populate list
    */
    $.ajax({
        error: function(XMLHttpRequest, textStatus, errorThrown) {
            alert(textStatus);
        },
        url: 'motors_names/' + this.session_id,
        type: 'GET',
        dataType: 'json',
        success: $.proxy(function(res) {
            var motors = res.motors;
            for (var i = 0; i < motors.length; i++) {
                var name = motors[i].name;
                var pos = motors[i].pos;
                var state = motors[i].state;
                var dom_item = $("<li></li>");
                dom_item.addClass("control-panel-item");
                this.update_item(dom_item, name, pos, state);
                this.motors_list.append(dom_item);
                this.motors[name] = {
                    dom_item: dom_item,
                    state: state,
                    pos: pos
                };
            }
        }, this)
    });
};

ControlPanel.prototype = {
    update_item: function(dom_item, name, label, state) {
        if (label != undefined) {
            dom_item.text(name + ": " + label);
        }
        if (state != undefined) {
            dom_item.removeClass("control-panel-item-ready control-panel-item-moving control-panel-item-fault");
            if (state == "READY") {
                dom_item.addClass("control-panel-item-ready");
            } else if (state == "MOVING") {
                dom_item.addClass("control-panel-item-moving");
            } else if (state == "FAULT") {
                dom_item.addClass("control-panel-item-fault");
            }
        }
    },
    update_display: function(data) {
        var dom_item = this.motors[data.name].dom_item
        this.update_item(dom_item, data.name, data.position, data.state);
    },

};
