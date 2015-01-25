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
            for (var i=0; i<res.length; i++) {
                this.motors_list.append($.parseHTML("<li class='control_panel_motor'>" + res[i].name + "</li>")); 
                this.motors[res[i].name]={ dom_item: this.motors_list.children().last(), state: res[i].state, pos: res[i].pos };
            }            
        }, this)
    }); 
};

ControlPanel.prototype = {
    _cmdline_handle_keypress: function(e) {
    },

};
