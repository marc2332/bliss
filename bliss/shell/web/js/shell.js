/*
function generateUUID() {
    var d = performance.now();
    var uuid = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        var r = (d + Math.random()*16)%16 | 0;
        d = Math.floor(d/16);
        return (c=='x' ? r : (r&0x3|0x8)).toString(16);
    });
    return uuid;
};

function readCookie(name) {
    var nameEQ = name + "=";
    var ca = document.cookie.split(';');
    for (var i = 0; i < ca.length; i++) {
        var c = ca[i];
        while (c.charAt(0) == ' ') c = c.substring(1, c.length);
        if (c.indexOf(nameEQ) == 0) return c.substring(nameEQ.length, c.length);
    }
    return null;
}
*/

function Shell(client_uuid, cmdline_div_id, shell_output_div_id, setup_div_id, log_div_id) {
    var table = $('<div style="width:100%; display:table;"></div>');
    this.hint_row = $($.parseHTML('<div style="display:table-row;"><label style="display:table-cell; width:1%;">&nbsp;</label></div>'));
    this.hint_row.appendTo(table);
    this.hint = $('<label class="hint" style="display:table-cell;"></label>');
    this.hint.appendTo(this.hint_row);
    this.cmdline_row = $($.parseHTML('<div style="display:table-row;"></div>'));
    this.cmdline_row.appendTo(table);
    this.cmdline_row.append($('<label style="display:table-cell; width:1%;" class="code-font">&gt;&nbsp;</label>'));
    this.cmdline = $('<input style="width:99%; border:none; display:table-cell;" class="code-font" autofocus></input>');
    this.cmdline.appendTo(this.cmdline_row);
    this.completion_row = $('<div style="display:table-row;"><label style="display:table-cell;"></label></div>');
    this.completion_list = $('<ul style="display:table-cell;" class="items-list"></ul>');
    this.completion_list.appendTo(this.completion_row);
    table.append(this.completion_row);
    this.editor_row = $($.parseHTML('<div style="display:none;"></div>'));
    this.editor_area = $($.parseHTML('<textarea style="width:99%; display:table-cell;"></textarea>'));
    this.editor_area.appendTo(this.editor_row);
    table.append(this.editor_row);
    $('#' + cmdline_div_id).append(table);

    this.output_div = $("#" + shell_output_div_id);
    this.output_div.css("overflow", "auto");
    this.output_div.addClass("code-font");
    this.last_output_div = $("<div></div>");
    this.output_div.prepend(this.last_output_div);

    this.setup_div = $("#" + setup_div_id);
    this.setup_div.addClass("code-font");
    this.setup_output_div = $("</div></div>");
    var resetup_btn = $("<button>Resetup</button>");
    resetup_btn.button().css("font-size", "0.8em");
    resetup_btn.on("click", $.proxy(function() { this.execute_setup(true) }, this));
    this.setup_div.append(resetup_btn);
    var new_setup_div = $("<div></div>");
    this.setup_div.append(new_setup_div);
    this.setup_div.css("overflow", "auto");
    this.setup_div = new_setup_div;
    this.setup_div.append(this.setup_output_div);

    this.logging_div = $("#" + log_div_id);
    this.logging_div.addClass("code-font");
    var clear_btn = $("<button>Clear</button>");
    clear_btn.button().css("font-size", "0.8em");
    clear_btn.on("click", $.proxy(function() { this.logging_div.empty(); }, this));
    this.logging_div.append(clear_btn);
    var new_logging_div = $("<div></div>");
    this.logging_div.append($("<hr>"));
    this.logging_div.append(new_logging_div);
    this.logging_div = new_logging_div;
    this.logging_div.css("overflow", "auto");
 
    this.client_uuid = client_uuid;
    this.executing = false;
    this.completion_mode = false;
    this.completion_selected_item_text = '';
    this._completions = [];
    this.session_id = this.get_session_id();
    this.history = JSON.parse(localStorage.getItem(this.session_id + "_shell_commands"));
    if (!this.history)
        this.history = [];
    this.history_index = this.history.length;
    this.current_command = "";
    this.plot = {};

    this.mousetrap = new Mousetrap(this.cmdline[0]); 
    this.bind_keys(this.mousetrap);

    /*
       ask to run initialization script, don't keep history
       and consider EOF as an error
    */
    this.set_executing(true);
    this.setup = this.execute_setup();
};

Shell.prototype = {
    get_session_id: function() {
        var url = document.URL;
        return url.substr(url.lastIndexOf('/') + 1)
    },

    handle_output_event: function(output) {
        if (output.type == 'plot') {
            this.output_div.parent().tabs("option", "active", 1);
            this.display_plot(output.data);
        } else if (output.type == 'setup') {
            this.display_output(output.data, 'auto', this.setup_output_div);
        } else if (output.type == 'log') {
            this.display_log(output.data);
        } else {
            this.output_div.parent().tabs("option", "active", 1);
            this.display_output(output.data);
        }
    },

    completion_request: function(text, index, dont_select_completion) {
        $.ajax({
            url: this.session_id+"/completion_request",
            dataType: "json",
            data: {
		"client_uuid": this.client_uuid,
                "text": text,
                "index": index
            },
            success: $.proxy(function(completion_ret, status, jqxhr) {
                this._completions = [];
                var completion_list = [];

                // filter underscores & private methods
                for (var i = 0; i < completion_ret.possibilities.length; i++) {
                    var c = completion_ret.possibilities[i];
                    if (c.substr(0, 1) != '_') {
                        completion_list.push(c);
                        this._completions.push(completion_ret.completions[i]);
                    }
                }
                for (var i = 0; i < completion_list.length; i++) {
                    this.completion_list.append($.parseHTML("<li class='completion-item'>" + completion_list[i] + "</li>"));
                }

                $("body").layout().resizeAll();

                if (!dont_select_completion) {
                    this._select_completion_item(0);
                }

                this.cmdline.focus();
            }, this)
        });
    },

    _select_completion_item: function(next_item) {
        var completion_items = this.completion_list.children();
        var selected_item_index = 0;
        var selected_item = null;

        completion_items.each(function(i, j) {
            if ($(this).hasClass("completion-item-selected")) {
                selected_item_index = i;
                $(this).removeClass("completion-item-selected");
            }
            $(this).addClass("completion-item");
        });
        if (next_item < 0) {
            selected_item_index = 0;
        } else {
            selected_item_index = (selected_item_index + next_item) % completion_items.length;
        }
        selected_item = $(completion_items[selected_item_index]);
        selected_item.addClass("completion-item-selected");
        this.completion_selected_item_text = selected_item.text();
        this._do_complete(selected_item_index);
    },

    _do_complete: function(completion_index) {
        if (this._completions.length == 0) return;
        var completion = this._completions[completion_index];
        this.cmdline.val(this.current_command.substr(0, this._completion_start) + completion + this.current_command.substr(this._completion_start));
        this.cmdline[0].selectionStart = this._completion_start + completion.length;
        this.cmdline[0].selectionEnd = this.cmdline[0].selectionStart;
        this.cmdline.focus();
    },

    bind_keys: function(mousetrap) {
        var self = this;
        mousetrap.bind("up", function() {
            if (! self.completion_mode) {
                self.history_index--;
                if (self.history_index <= 0) {
                    self.history_index = 0;
                    self.cmdline.val(self.current_command);
                } else
                    self.cmdline.val(self.history[self.history_index]);
            }
            return false;
        });
        mousetrap.bind("down", function() {
            if (! self.completion_mode) {
                self.history_index++;
                if (self.history_index >= self.history.length) {
                    self.history_index = self.history.length;
                    self.cmdline.val(self.current_command);
                } else
                    self.cmdline.val(self.history[self.history_index]);
            }
            return false; 
        });
        mousetrap.bind("left", function() {
            if (self.completion_mode) {
                self._select_completion_item(-1);
                self.cmdline.focus();
                return false;
            }
        }); 
        mousetrap.bind("right", function() {
            if (self.completion_mode) {
                self._select_completion_item(+1);
                self.cmdline.focus();
                return false;
            }
        });
        mousetrap.bind("esc", function() {
            if (self.completion_mode) {
                self.completion_mode = false;
                self.completion_list.empty();
                $("body").layout().resizeAll();
                self.cmdline.focus();
                return false;
            }
        });
        mousetrap.bind("enter", function() {
            if (self.completion_mode) {
                self.completion_mode = false;
                self.completion_list.empty();
                $("body").layout().resizeAll();
                self.cmdline.focus();
                return false;
            } else if (self.executing) {
                return false;
            } else {
                self.hint.text("");
                self.execute(self.cmdline.val());
            };
        });
        mousetrap.bind("ctrl+c", function() {
            if (self.executing) {
                self.send_abort();
                return false;
            }
        });
        mousetrap.bind("(", function() {
            // open parenthesis
            var code = self.cmdline.val().substr(0, self.cmdline[0].selectionStart);
            $.ajax({
                    url: self.session_id+"/args_request",
                    dataType: "json",
                    data: {
                        "client_uuid": self.client_uuid,
                        "code": code,
                    },
                    success: $.proxy(function(ret, status, jqxhr) {
                       if (ret.func) {
                           self.hint.text(ret.func_name + ret.args); //alert(ret.args);
                       }
                    }, self)
            });
        });
        mousetrap.bind(".", function() {
            self.current_command = self.cmdline.val()+'.';
            self._completion_start = self.cmdline[0].selectionStart+1;
            self.completion_mode = true;
            self.completion_request(self.current_command, self._completion_start, true);
        });
        mousetrap.bind("tab", function() {
            self.current_command = self.cmdline.val();
            self._completion_start = self.cmdline[0].selectionStart;
            self.completion_mode = true;
            self.completion_request(self.current_command, self._completion_start);
            return false;
        });
        mousetrap.bind("*", function() {
            if (self.completion_mode) {
                self.completion_mode = false;
                self.completion_list.empty();
                $("body").layout().resizeAll();
                self.cmdline.focus();
            }
            self.history_index = self.history.length;
            self.current_command = self.cmdline.val();
        });
    },

    set_executing: function(executing) {
        this.executing = executing
        if (executing) {
            this.cmdline.addClass("cmdline-executing");
        } else {
            this.cmdline.removeClass("cmdline-executing");
            this.last_output_div.removeClass("output-executing");
        }
    },

    /*scrollToBottom: function(jq_div) {
        var sHeight = jq_div[0].scrollHeight;
        //Scrolling the element to the sHeight
        jq_div.scrollTop(sHeight);
    },*/

    execute: function(code) {
        this.set_executing(true);
        this.cmdline.val('');
        if (this.last_output_div) { 
            this.last_output_div.removeClass("output-executing");
        }
        this.last_output_div = $("<div></div>");
        this.output_div.prepend(this.last_output_div);
        var pre = $("<pre></pre>");
        pre.html("&gt;&nbsp;");
        var i = $("<i></i>");
        i.text(code);
        pre.append(i);
        this.last_output_div.append(pre);
        //this.last_output_div.append($("<pre>&gt;&nbsp;<i>" + this._html_escape(code) + "</i></pre>"));
        this.last_output_div.addClass("output-executing");
        this.output_div.scrollTop(0);

        this._execute(code);
    },

    execute_setup: function(force) {
        if (force == undefined) { force = false; }

        this.setup_output_div = $("<div></div>");
        this.setup_div.prepend(this.setup_output_div);
        //this.setup_div.prepend($("<pre>"+moment().format("dddd, MMMM Do YYYY, hh:mm:ss")+"&gt;&nbsp;<i>Executing setup...</i></pre><hr>"));
        this.setup_div.prepend($("<hr>"));

        return this._execute("setup", force, true);
    },

    _execute: function(cmd, save_history, eof_error) {
        var url = this.session_id+'/command';
        var data = { "client_uuid": this.client_uuid };

        /* save history */
        if (save_history == undefined) { save_history = true; }
        if (save_history) {
            this.history.push(cmd);
            this.history_index = this.history.length;
            localStorage[this.session_id + "_shell_commands"] = JSON.stringify(this.history);
        }

        if (cmd == "setup") {
            url = this.session_id + '/setup';
            data["force"] = save_history;
        } else {
            data["code"] = cmd;
        }

        /* make remote call */
        return $.ajax({
            error: $.proxy(function(XMLHttpRequest, textStatus, errorThrown) {
                this.set_executing(false);
                alert(textStatus);
            }, this),
            url: url,
            type: 'GET',
            dataType: 'json',
            success: $.proxy(function(res) {
                this.set_executing(false);
                if (res.error.length > 0) {
                    if ((!eof_error) && (res.error == "EOF")) {
                        /* erase last added echo output */
                        this.output_div.children().last().remove();

                        var cmdline = this.cmdline;
                        var editor_row = this.editor_row;
                        editor_row.css("display", "table-row");
                        var cmdline_row = this.cmdline_row;
                        cmdline_row.css("display", "none");
                        var editor_area = this.editor_area;
                        editor_area.val(res.input);
                        var execute = $.proxy(this.execute, this);

                        var editor = CodeMirror.fromTextArea(editor_area[0], {
                            lineNumbers: true,
                            mode: {
                                name: "text/x-python",
                                version: 2,
                            },
                            autofocus: true,
                            extraKeys: {
                                'Ctrl-Enter': function() {
                                    editor.toTextArea();
                                    var code_text = editor_area.val();
                                    editor_row.css("display", "none");
                                    cmdline_row.css("display", "table-row");
                                    execute(code_text);
                                },
                                'Esc': function() {
                                    editor.toTextArea();
                                    editor_row.css("display", "none");
                                    cmdline_row.css("display", "table-row");
                                    cmdline.focus();
                                }
                            }
                        });

                        editor.execCommand("goDocEnd");
                    } else {
                        var that = this;
                        if (cmd=='setup') {
                            window.setTimeout(function() {that.display_output(res.error, 'red', that.setup_output_div)}, 100);
                        } else {
                            window.setTimeout(function() {that.display_output(res.error, 'red')}, 100);
                        }
                    }
                }
                this.cmdline.focus();
            }, this),
            data: data
        });
    },

    display_output: function(output, color, output_div) {
        if (output_div == undefined) { output_div = this.last_output_div };
        if (color == undefined) { color = "auto"; };

        var pre = $("<pre></pre>");
        pre.css("margin", "0px");
        if (color != "auto") { pre.css("color", color); }
        pre.css("display", "inline");
        pre.text(output);
        output_div.append(pre);
        output_div.parent().scrollTop(0);
        //this.scrollToBottom(this.output_div);
    },

    display_plot: function(data) {
        if (this.plot[data.scan_id]) {
            /* update existing plot */
            var plot = this.plot[data.scan_id];
            if (data.values) {
                plot.data.push(data.values);
                if (plot.obj) {
                    plot.obj.updateOptions({
                        'file': plot.data
                    });
                } else {
                    var fs = parseInt(this.cmdline.css("font-size"));
                    plot.obj = new Dygraph(plot.div, plot.data, {
                        title: plot.title,
                        titleHeight: 2*fs,
                        labels: plot.labels,
                        legend: "always",
                        axisLabelFontSize: fs,
                        xLabelHeight: fs,
                        yLabelWidth: fs
                    });
                    plot.div.addEventListener("mouseup", function(e) {
                        plot.obj.resize();
                    });
                }
            } else {
                /* end of scan, free memory */
                delete this.plot[data.scan_id];
            }
        } else {
            /* create new plot */
            var plot_div = $('<div class="ui-widget-content" style="width:640px; height:480px; resize:both; overflow: auto;"></div>');
            //plot_div.resizable(); this doesn't work... why?
            this.last_output_div.append(plot_div);
            this.output_div.scrollTop(0);
            //this.scrollToBottom(this.output_div);
            this.plot[data.scan_id] = {
                "div": plot_div[0],
                "data": [],
                "obj": null,
                "title": data.filename,
                "labels": [data.scan_actuators[0]].concat(data.counters)
            };
        }
    },

    display_log: function(data) {
        this.logging_output_div = $("<div></div>");
        this.logging_div.prepend(this.logging_output_div);
        if (data.level == "DEBUG") {
            color = "green";
        } else if (data.level == "INFO") {
            color = "blue";
        } else if (data.level == "WARNING") {
            color = "orange";
        } else {
            color = "red";
        }
        this.display_output(data.message, color, this.logging_output_div);
    },

    send_abort: function() {
        $.ajax({
            url: this.session_id+'/abort',
            type: 'GET',
            success: function() {}
        });
    }

};
