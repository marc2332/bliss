function Synoptic(session_id, client_uuid, div_id) {
    this.motors = {};
    this.actuators = {};
    this.shutters = {};

    this.session_id = session_id;
    this.client_uuid = client_uuid;
    this.parent_div = $(document.getElementById(div_id));
    this.top_div = $("<div></div>");
    //this.top_div.css("background", "#ffff00");
    //this.top_div.css("border", "1px solid black");
    this.top_div.css("width", "100%");
    this.bottom_div = this.top_div.clone();
    //this.bottom_div.css("background", "#00ffff");
    this.synoptic_div = $("<div></div>");

    this.parent_div.load(this.session_id + "/synoptic", $.proxy(function() {
        var svg = this.parent_div.find("svg");
        this.svg = svg[0];
        svg.css("height", this.parent_div.height() * 0.8);
        svg.css("display", "block");
        svg.css("margin", "auto");
        this.parent_div.prepend(this.top_div);
        this.parent_div.append(this.bottom_div);
        this.svg.onload = this.initialize();
    }, this));
};

Synoptic.prototype = {

    get_cols: function() {
        var cols = $(this.svg).find("g").sort(function(a, b) {
            var a_rect = $(a)[0].getBoundingClientRect();
            var b_rect = $(b)[0].getBoundingClientRect();
            return a_rect.left - b_rect.left
        }).filter(function(i,elt) {
            return /^g[0-9]+$/.test(this.id) === false; 
        });
        
        return cols;
    },

    handle_data_event: function(data) {
        this.update_display(data);
    },

    load_objects: function() {
        $.ajax({
            error: function(XMLHttpRequest, textStatus, errorThrown) {
                alert(textStatus);
            },
            url: this.session_id + '/synoptic/objects',
            type: 'GET',
            dataType: 'json',
            data: {
                client_uuid: this.client_uuid
            },
            success: $.proxy(function(objects_by_svg_group) {
                 for (var group_name in objects_by_svg_group) {
                     for (var i = 0; i < objects_by_svg_group[group_name].top.length; i++) {
                         var obj = objects_by_svg_group[group_name].top[i]
                         this.add_object(group_name, 'top', obj);
                     }
                     for (var i = 0; i < objects_by_svg_group[group_name].bottom.length; i++) {
                         var obj = objects_by_svg_group[group_name].bottom[i]
                         this.add_object(group_name, 'bottom', obj);
                     }
                 }
           }, this)
        });
    },

    add_object: function(group_name, where, obj) {
        var container = $("#" + group_name + "__" + where)
        if (obj.type == 'counter') {
            var dom_item = $("<li></li>");
            dom_item.html("&nbsp;" + obj.name + "&nbsp;");
            dom_item.addClass("control-panel-item");
            container.append(dom_item);
        } else if (obj.type == 'motor') {
            var name = obj.name;
            var pos = obj.position;
            var state = obj.state;
            var dom_item = $("<li></li>");
            dom_item.addClass("control-panel-item");
            container.append(dom_item);
            this.motors[name] = {
                name: name,
                dom_item: dom_item,
                state: state,
                position: pos
            }
            this.update_motor(this.motors[name]);
        } else if (obj.type == 'actuator') {
            var name = obj.name;
            var state = obj.state;
            this.actuators[name] = {
                name: name,
                state: state
            }
            var dom_item = this.add_item_with_buttons(this.actuators, name, "In", "set_in", "Out", "set_out");
            container.append(dom_item);
            this.update_inout(this.actuators[name]);
        } else if (obj.type == 'shutter') {
            var name = obj.name;
            var state = obj.state;
            this.shutters[name] = {
                name: name,
                state: state
            }
            var dom_item = this.add_item_with_buttons(this.shutters, name, "Open", "open", "Close", "close");
            container.append(dom_item);
            this.update_shutter(this.shutters[name]);
        }
    },

    initialize: function() {
        var self = this;
        /*svg.mousewheel(function(event) {
            console.log(event.deltaX, event.deltaY, event.deltaFactor);
            $(self.svg).css("height", $(self.svg).css("height")+event.deltaFactor);
            self.rearrange();
        });
        */

        this.get_cols().each(function() {
            var col_id = this.id;
            var ul = $("<ul></ul>");
            ul.addClass("items-list");
            ul.attr("id", col_id + "__top");
            //ul.css("border", "1px solid black");
            //ul.css("vertical-align", "bottom");
            ul.css("position", "absolute");
            ul.css("display", "inline-block");
            var g_rect = this.getBoundingClientRect();
            ul.css("left", g_rect.left);
            ul.css("width", g_rect.width);
            self.top_div.append(ul);
            var ul2 = ul.clone();
            ul2.attr("id", col_id + "__bottom");
            //ul2.css("vertical-align", "top");
            self.bottom_div.append(ul2);
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
            $.get(session_id + "/synoptic/run/" + name + "/" + cmd1);
        });
        btn2.click(function() {
            $.get(session_id + "/synoptic/run/" + name + "/" + cmd2);
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
