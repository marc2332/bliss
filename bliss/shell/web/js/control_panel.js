function ControlPanel(div_id, session_id) {
    this.motors = {};
    this.session_id = session_id;

    this.motors_div = $('<div></div>');
    this.motors_list = $('<ul></ul>');
    this.motors_div.append(this.motors_list);
    $('#' + div_id).append(this.motors_div);

    /* 
       connect to control panel events stream 
    */
    this.output_stream = new EventSource('control_panel_events/' + this.session_id);
    this.output_stream.onmessage = $.proxy(function(e) {
        /*if (e.data) {
            var output = JSON.parse(e.data);
            if (output.type == 'plot') {
                this.display_plot(output.data);
            } else {
                this.display_output(output.data);
            }
        }*/
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
            for (var i=0; i<motors.length; i++) {
                var name = motors[i].name;
                var pos = motors[i].pos;
                var state = motors[i].state;
                var item_text = name + ": " + pos;
                var dom_item = $("<li class='control-panel-item'>" + item_text + "</li>");
                this.motors_list.append(dom_item); 
                if (state == "READY") {
                    dom_item.addClass("control-panel-item-ready");
                } else if (state == "MOVING") {
                    dom_item.addClass("control-panel-item-moving");
                }
                this.motors[name]={ dom_item: dom_item, state: state, pos: pos };
            }            
        }, this)
    }); 
};

ControlPanel.prototype = {
    _cmdline_handle_keypress: function(e) {
    },

};
