var term;
var term_div;

var fireOffCmd = function (cmd, multiline) {
    $.ajax({
        error: function (XMLHttpRequest, textStatus, errorThrown) {},
        url: 'command',
        type: 'GET',
        success: function (res) {
            if (res.error.length > 0) {
                if (res.error == "EOF") {
                    term.pause();
		    term_div.append("<textarea id='editor'>"+res.input+"</textarea>"); 
                    var editor = CodeMirror.fromTextArea(document.getElementById("editor"), { lineNumbers: true, mode: {name: "text/x-cython",
               version: 2,  }, autofocus: true });
                    editor.execCommand("goDocEnd");
                    term_div.append("<button id='exec_code' type='button'>Execute</button><button id='close_code' type='button'>Close</button>");
                    $("#close_code").click(function () {
                        editor.toTextArea();
                        $("#editor").remove();
                        $("#exec_code").remove();
                        $("#close_code").remove();
                        createTerminal(term_div, term.session_id, true);
                    });
                    $("#exec_code").click(function () {
                        editor.toTextArea();
                        var code_text = $("#editor").val();
                        $("#editor").remove();
                        $("#exec_code").remove();
                        $("#close_code").remove();
                        createTerminal(term_div, term.session_id, true);
                        term.echo(code_text);
                        fireOffCmd(code_text, true);
                    });
                    return;
                } else {
                    term.error(res.error);
                }
            }
            term.executing = false;
            term.set_prompt("> ");
        },
        data: {
            "client_id": term.session_id,
            "code": cmd,
            "multiline": multiline
        },
        dataType: 'json'
    });
}

var askForOutput = function () {
    $.ajax({
        error: function (XMLHttpRequest, textStatus, errorThrown) {},
        url: 'output_request',
        type: 'GET',
        success: function (output) {
            term.echo(output);
        },
        complete: function () {
            askForOutput();
        },
        data: {
            "client_id": term.session_id
        },
        dataType: 'json'
    });
}

var abortExecution = function () {
    $.ajax({
        url: 'abort',
        type: 'GET',
        async: false,
        data: {
            "client_id": term.session_id
        },
        dataType: 'json'
    });
}

var askForLogMessages = function () {
    $.ajax({
        error: function (XMLHttpRequest, textStatus, errorThrown) {},
        url: 'log_msg_request',
        type: 'GET',
        success: function (msg) {
            jQuery("#logger:first").append("<p>" + msg + "</p>");
        },
        complete: function () {
            askForLogMessages();
        },
        data: {
            "client_id": term.session_id
        },
        dataType: 'json'
    });
}


function createTerminal(parent_div, session_id, dontaskforoutput) {
    term_div = parent_div;
    parent_div.append("<div></div>")
    term = parent_div.children().last().terminal(
        function (command, term) {
            if (command != '') {
                term.executing = true;
                term.set_prompt("");
                fireOffCmd(command);
            }
        }, {
            greetings: '',
            prompt: '> ',
            //height: 600,
            keypress: function (e, term) {
                if (term.paused()) return true;

                if (e.ctrlKey && e.which === 99) { // CTRL+C
                    abortExecution();
                    return false;
                }
                if (term.executing) return false;
                else return true;
            },
            tabcompletion: true,
            completion: function (term, string, callback) {
                term.disable();
                $.ajax({
                    error: function (XMLHttpRequest, textStatus, errorThrown) {},
                    url: 'completion_request',
                    type: 'GET',
                    success: function (res) {
                        term.enable();
                        callback(res.possibilities);
                    },
                    data: {
                        "client_id": term.session_id,
                        "text": string
                    },
                    dataType: 'json'
                });
            }
        });

    term.executing = false;
    term.session_id = session_id;

    if (! dontaskforoutput) askForOutput();
};
