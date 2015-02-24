/*
var askForLogMessages = function() {
    $.ajax({
        error: function(XMLHttpRequest, textStatus, errorThrown) {},
        url: 'log_msg_request',
        type: 'GET',
        success: function(msg) {
            jQuery("#logger:first").append("<p>" + msg + "</p>");
        },
        complete: function() {
            askForLogMessages();
        },
        data: {
            "client_id": term.session_id
        },
        dataType: 'json'
    });
}
*/

function Shell(cmdline_div_id, shell_output_div_id) {
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
    this.output_div.addClass("code-font");
    this.last_output_div = $("<div></div>");
    this.output_div.prepend(this.last_output_div);

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

    /* 
       connect to output stream, 
       to get output from server
    */
    this.output_stream = new EventSource(this.session_id+'/output_stream');
    this.output_stream.onmessage = $.proxy(function(e) {
        if (e.data) {
            var output = JSON.parse(e.data);
            if (output.type == 'plot') {
                this.display_plot(output.data);
            } else {
                this.display_output(output.data);
            }
        }
    }, this);

    /*
       this is just for escaping text into valid HTML
       (see _html_escape function)
    */
    this.DOMtext = document.createTextNode("text");
    this.DOMnative = document.createElement("span");
    this.DOMnative.appendChild(this.DOMtext);

    /* 
       jquery override 'this', that's just crazy!
       let methods have the proper 'this' 
    */
    this._cmdline_handle_keydown = $.proxy(this._cmdline_handle_keydown, this);
    this._cmdline_handle_keypress = $.proxy(this._cmdline_handle_keypress, this);
    this._cmdline_handle_keyup = $.proxy(this._cmdline_handle_keyup, this);

    this.cmdline.keypress(this._cmdline_handle_keypress);
    this.cmdline.keydown(this._cmdline_handle_keydown);
    this.cmdline.keyup(this._cmdline_handle_keyup);

    /*
       ask to run initialization script, using the special
       command "__INIT_SCRIPT__", don't keep history and
       consider EOF as an error
    */
    this.set_executing(true);
    this._execute("__INIT_SCRIPT__", true, true, false);
};

Shell.prototype = {
    get_session_id: function() {
        var url = document.URL;
        return url.substr(url.lastIndexOf('/') + 1)
    },

    completion_request: function(text, index, dont_select_completion) {
        $.ajax({
            url: this.session_id+"/completion_request",
            dataType: "json",
            data: {
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

    _cmdline_handle_keydown: function(e) {
            if (this.completion_mode) {
                if ((e.which == 38) || (e.which == 40)) {
                    /*
                       do not allow up/down arrow keys in
                       completion mode, since it would exit
                       completion mode - it's too easy
                       to press them by mistake
                       while navigating through propositions
                    */
                    e.preventDefault();
                } else if (e.which == 37) {
                    // key left
                    e.preventDefault();
                    this._select_completion_item(-1);
                    this.cmdline.focus();
                } else if (e.which == 39) {
                    // key right
                    e.preventDefault();
                    this._select_completion_item(+1);
                    this.cmdline.focus();
                } else {
                    this.completion_mode = false;
                    this.completion_list.empty();
                    if ((e.which === 27) || (e.which == 13)) {
                        e.preventDefault();
                    }
                    this.cmdline.focus();
                }
            } else {
                if (e.which === 38) {
                    this.history_index--;
                    if (this.history_index <= 0) {
                        this.history_index = 0;
                        this.cmdline.val(this.current_command);
                    } else
                        this.cmdline.val(this.history[this.history_index]);
                } else if (e.which == 40) {
                    this.history_index++;
                    if (this.history_index >= this.history.length) {
                        this.history_index = this.history.length;
                        this.cmdline.val(this.current_command);
                    } else
                        this.cmdline.val(this.history[this.history_index]);
                } else if (e.which == 9) {
                    e.preventDefault();
                    this.current_command = this.cmdline.val();
                    this._completion_start = this.cmdline[0].selectionStart;
                    this.completion_mode = true;
                    this.completion_request(this.current_command, this._completion_start);
                } else {
                    this.history_index = this.history.length;
                    this.current_command = this.cmdline.val();
                }
            }
    },

    _cmdline_handle_keyup: function(e) {
            if (!this.completion_mode) {
                if (e.which == 190) {
                    this.current_command = this.cmdline.val();
                    this._completion_start = this.cmdline[0].selectionStart;
                    this.completion_mode = true;
                    this.completion_request(this.current_command, this._completion_start, true);
                }
            }
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

    _cmdline_handle_keypress: function(e) {
        if (e.ctrlKey && e.which === 99) {
            e.preventDefault();
            if (this.executing) {
                this.send_abort();
            }
        } else {
                if (e.which == 13) {
                    if (this.executing) { e.preventDefault(); } 
                    else {
                      this.hint.text("");
                      if (this.completion_mode) {
                          e.preventDefault();
                      } else {
                          this.execute(this.cmdline.val());
                      }
                    } 
                } else if (e.which == 40) {
                    // open parenthesis
                    var code = this.cmdline.val().substr(0, this.cmdline[0].selectionStart);
                    $.ajax({
                        url: this.session_id+"/args_request",
                        dataType: "json",
                        data: {
                            "code": code,
                        },
                        success: $.proxy(function(ret, status, jqxhr) {
                            if (ret.func) {
                                this.hint.text(ret.func_name + ret.args); //alert(ret.args);
                            }
                        }, this)
                    });
                } else if (e.which == 190) {
                    // period '.'
                    if (!this.completion_mode) {
                        this.current_command = this.cmdline.val();
                        this._completion_start = this.cmdline[0].selectionStart;
                        this.completion_mode = true;
                        this.completion_request(this.current_command, this._completion_start, true);
                    }
                }
        }
    },

    scrollToBottom: function(jq_div) {
        var sHeight = jq_div[0].scrollHeight;
        //Scrolling the element to the sHeight
        jq_div.scrollTop(sHeight);
    },

    execute: function(code) {
        this.set_executing(true);
        this.cmdline.val('');
        if (this.last_output_div) { 
            this.last_output_div.removeClass("output-executing");
        }
        this.last_output_div = $("<div></div>");
        this.output_div.prepend(this.last_output_div);
        this.last_output_div.append($("<pre>&gt;&nbsp;<i>" + this._html_escape(code) + "</i></pre>"));
        //var last_element = $("<pre>&gt;&nbsp;<i>" + this._html_escape(code) + "</i></pre>");
        //this.output_div.append(last_element);
        //this.scrollToBottom(this.output_div);
        this.last_output_div.addClass("output-executing");
        this.output_div.scrollTop(0);
        this._execute(code);
    },

    _execute: function(cmd, dont_save_history, eof_error, synchronous_call) {
        /* save history */
        if (!dont_save_history) {
            this.history.push(cmd);
            this.history_index = this.history.length;
            localStorage[this.session_id + "_shell_commands"] = JSON.stringify(this.history);
        }

        if (synchronous_call == undefined) {
            synchronous_call = true;
        }

        /* make remote call */
        $.ajax({
            error: function(XMLHttpRequest, textStatus, errorThrown) {
                this.set_executing(false);
                alert(textStatus);
            },
            url: this.session_id+'/command',
            type: 'GET',
            dataType: 'json',
            async: synchronous_call,
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
                                name: "text/x-cython",
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
                        this.display_output(res.error, true);
                    }
                }
                this.cmdline.focus();
            }, this),
            data: {
                "code": cmd,
            },
        });
    },

    _html_escape: function(text) {
        this.DOMtext.nodeValue = text;
        return this.DOMnative.innerHTML;
    },

    display_output: function(output, error) {
        var last_element;
        if (error) {
            last_element = $('<pre><font color="red">' + this._html_escape(output) + '</font></pre>');
            this.last_output_div.append(last_element);
        } else {
            var output_pre = $('<pre></pre>');
            output_pre.text(output);
            output_pre.css({
                display: "inline"
            });
            this.last_output_div.append(output_pre);
        }
        this.output_div.scrollTop(0);
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

    send_abort: function() {
        $.ajax({
            url: this.session_id+'/abort',
            type: 'GET',
            success: function() {}
        });
    }

};
