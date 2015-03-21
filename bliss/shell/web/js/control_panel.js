function Synoptic(control_panel, div_id) {
    this.control_panel = control_panel;

    this.top_div = $("<table style='background: #ffff00; width:100%; height:10%; table-layout: fixed'></table>");
    this.top_div.append($("<colgroup></colgroup>"));
    this.bottom_div = this.top_div.clone();
    this.bottom_div.css("background", "#00ffff");
    this.bottom_div.css("border","1px solid black");
    this.bottom_div.append($("<colgroup></colgroup>"));

    $("#"+div_id).load(this.control_panel.session_id+"/synoptic", $.proxy(function() {
      parent_div = $("#"+div_id);
      var svg = parent_div.find("svg");
      this.svg = svg[0];
      svg.css("height", "75%");
      svg.css("width", "100%");

      parent_div.prepend(this.top_div);
      parent_div.append(this.bottom_div);

      var tr = $("<tr></tr>");
      var tr2 = $("<tr></tr>");
      var self = this;
      this.bottom_div.append(tr);
      this.top_div.append(tr2);
      this.get_cols().each(function() { 
          var col_id = $(this)[0].id;
          if (col_id != '') {
              var col = $("<td></td>");
              col.css("border", "1px solid black");
              col.append(self.control_panel.motors_list.clone());
              tr.append(col);
              tr2.append(col.clone());
              tr.append($("<td></td>"));
              tr2.append($("<td></td>"));
          }
      });
      
      window.addResizeListener(parent_div[0], function() { self.rearrange(); }); 

      this.rearrange();
    }, this));
};

Synoptic.prototype = {

    get_cols: function() {
        var cols = $(this.svg).find("g").sort(function(a,b) { 
             var a_rect = $(a)[0].getBoundingClientRect();
             var b_rect = $(b)[0].getBoundingClientRect();
             return a_rect.left-b_rect.left
        });
        return cols; 
    },

    rearrange: function() {
        var colgroup = $(this.bottom_div.find("colgroup")[0]);
        var colgroup2 = $(this.top_div.find("colgroup")[0]);
        colgroup.empty();
        colgroup2.empty();

        var width = 0;
        var x = 0;
        var cols = this.get_cols();
        for (var i=0; i<cols.length; i++) {
             var col = $(cols[i])[0]; 
             var g_rect = col.getBoundingClientRect();
             if (g_rect.width > width) { 
                 x = g_rect.left;
                 width = g_rect.width; 
             }
             if (col.id != '') {
               var new_col = $("<col>");
               new_col.css("width", g_rect.width);
               colgroup.append(new_col);
               colgroup2.append(new_col.clone());
               if (i<cols.length-1) {
                   var new_col = $("<col>");
                   next_g_rect = $(cols[i+1])[0].getBoundingClientRect();
                   new_col.css("width", next_g_rect.left-g_rect.right);
                   colgroup.append(new_col);
                   colgroup2.append(new_col.clone());
               }
             }
        };
     
        this.bottom_div.css("width", width);
        this.bottom_div.css("position", "relative"); 
        this.bottom_div.css("left", x);
        this.top_div.css("width", width);
        this.top_div.css("position", "relative"); 
        this.top_div.css("left", x);
    }
};

function ControlPanel(session_id, client_uuid, div_id) {
    this.motors = {};
    this.actuators = {};
    this.shutters = {};
    this.session_id = session_id;
    this.client_uuid = client_uuid;

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
    this.output_stream = new EventSource(this.session_id + '/control_panel_events/'+this.client_uuid);
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
            data: { client_uuid: this.client_uuid },
            success: $.proxy(function(res) {
                var counters = res.counters;
                for (var i = 0; i<counters.length; i++) {
                   var name = counters[i].name;
                   var dom_item = $("<li></li>");
                   dom_item.html("&nbsp;" + name + "&nbsp;");
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
                    this.update_shutter(this.shutters[name]);
                }
            }, this)
        });
    },

    add_item_with_buttons: function(obj_dict, name, label1, cmd1, label2, cmd2) {
        var session_id = this.session_id;
        var dom_item = $("<li></li>");
        dom_item.addClass("control-panel-item");
        var btn1 = $("<span>&nbsp;" + label1 + "&nbsp;</span>");
        btn1.addClass("control-panel-toggle");
        var btn2 = btn1.clone();
        btn2.html("&nbsp;" + label2 + "&nbsp;");
        btn1.click(function() {
            $.get(session_id + "/control_panel/run/" + name + "/" + cmd1);
        });
        btn2.click(function() {
            $.get(session_id + "/control_panel/run/" + name + "/" + cmd2);
        });
        dom_item.html(name + "&nbsp;");
        dom_item.append(btn2);
        dom_item.append(btn1);
        var obj = obj_dict[name];
        obj.dom_item = dom_item;
        obj.btn1 = btn1;
        obj.btn2 = btn2;
        return (dom_item);
    },

    update_motor: function(motor) {
        var name = motor.name;
        var state = motor.state;
        var pos = motor.position;
        var dom_item = motor.dom_item;

        dom_item.html(name + "&nbsp;" + pos);
        
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
        var btn1 = actuator.btn1;
        var btn2 = actuator.btn2;
        btn1.removeClass("control-panel-toggle-pressed");
        btn2.removeClass("control-panel-toggle-pressed");

        if (state == "IN") {
            btn1.addClass("control-panel-toggle-pressed");
        } else if (state == "OUT") {
            btn2.addClass("control-panel-toggle-pressed");
        }
    },

    update_shutter: function(shutter) {
        var state = shutter.state;
        var btn1 = shutter.btn1;
        var btn2 = shutter.btn2;
        btn1.removeClass("control-panel-toggle-pressed");
        btn2.removeClass("control-panel-toggle-pressed");

        if (state == "OPENED") {
            btn1.addClass("control-panel-toggle-pressed");
        } else if (state == "CLOSED") {
            btn2.addClass("control-panel-toggle-pressed");
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
