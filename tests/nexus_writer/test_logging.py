# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import re
import subprocess
import pprint
import difflib
import itertools
from collections import OrderedDict


differ = difflib.Differ()

linesepstr = os.linesep.encode("unicode-escape").decode()


def codefilename(tmpdir):
    return os.path.join(str(tmpdir), "test.py")


def outfilename(tmpdir):
    return os.path.join(str(tmpdir), "out.log")


def errfilename(tmpdir):
    return os.path.join(str(tmpdir), "err.log")


def allfilename(tmpdir):
    return os.path.join(str(tmpdir), "all.log")


def read_file(filename):
    try:
        with open(filename, "r") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def read_files(tmpdir):
    return (
        read_file(allfilename(tmpdir)),
        read_file(outfilename(tmpdir)),
        read_file(errfilename(tmpdir)),
    )


def generate_test_script(tmpdir, createlogger=False, **kwargs):
    lines = ["import sys"]
    if createlogger:
        lines += [
            "from nexus_writer_service.utils import logging_utils as utils",
            "logger = utils.getLogger(__name__, __file__, help=True)",
        ]
    else:
        lines += ["import logging", "logger = logging.getLogger(__name__)"]
    lines += [
        'logger.critical("CRITICAL")',
        'logger.error("ERROR")',
        'logger.warning("WARNING")',
        'logger.info("INFO")',
        'logger.debug("DEBUG")',
    ]
    if createlogger:
        lines += ['utils.print_out("PRINTOUT")', 'utils.print_err("PRINTERR")']
    lines += [
        'print("PRINT")',
        'print("")',
        r'print("A{}B{}", "C"*10, [1,2,3])'.format(linesepstr, linesepstr),
        r'sys.stdout.write("STDOUTWRITE{}")'.format(linesepstr),
        "sys.stdout.flush()",
        r'sys.stderr.write("STDERRWRITE{}")'.format(linesepstr),
        "sys.stderr.flush()",
    ]
    filename = codefilename(tmpdir)
    with open(filename, mode="w") as f:
        for line in lines:
            f.write(line + os.linesep)
    return filename


# Expected output of the test script for `expected_std`
expected_lines = OrderedDict()
expected_lines["CRITICAL"] = "CRITICAL", "CRITICAL:{}: "
expected_lines["ERROR"] = "ERROR", "ERROR:{}: "
expected_lines["WARNING"] = "WARNING", "WARNING:{}: "
expected_lines["INFO"] = "INFO", "INFO:{}: "
expected_lines["DEBUG"] = "DEBUG", "DEBUG:{}: "
expected_lines["PRINTOUT"] = "PRINTOUT", ""
expected_lines["PRINTERR"] = "PRINTERR", ""
expected_lines["PRINT1"] = "PRINT", ""
expected_lines["PRINT2"] = "", ""
expected_lines["PRINT3"] = (
    "A{}B{} CCCCCCCCCC [1, 2, 3]".format(os.linesep, os.linesep),
    "",
)
expected_lines["STDOUTWRITE"] = "STDOUTWRITE", ""
expected_lines["STDERRWRITE"] = "STDERRWRITE", ""

logger_out_lines = ["DEBUG", "INFO"]
logger_err_lines = ["WARNING", "ERROR", "CRITICAL"]  # These have stderr as fallback
logger_lines = logger_out_lines + logger_err_lines
util_out_lines = ["PRINTOUT"]
util_err_lines = ["PRINTERR"]
util_lines = util_out_lines + util_err_lines
lines_need_logger = logger_out_lines + util_lines
std_out_lines = ["STDOUTWRITE"]
std_err_lines = ["STDERRWRITE"]
std_lines = std_out_lines + std_err_lines
print_lines = ["PRINT1", "PRINT2", "PRINT3"]
out_lines = logger_out_lines + util_out_lines + std_out_lines + print_lines
err_lines = logger_err_lines + util_err_lines + std_err_lines

log_levels = logger_lines


def expected_std(
    outtype=None,
    file=None,
    level=None,
    std=None,
    redirectstd=None,
    createlogger=None,
    **kwargs,
):
    """
    :param outtype str: out, err or all
    :param bool file: lines in file or stdout/stderr
    :param level:
    :param bool or tuple std: logging to stdout/stderr enabled
    :param bool or tuple redirectstd: redirect stdout/stderr to dedicated loggers
    """
    lines = []
    if outtype == "out":
        other_stream = err_lines
    elif outtype == "err":
        other_stream = out_lines
    else:
        other_stream = []
        redirectstdout, redirectstderr = redirectstd
    for desc, (msg, prefix) in expected_lines.items():
        if desc in other_stream:
            continue
        if createlogger:
            if file:
                # expected log file content
                if other_stream:
                    # out or err log file
                    if not redirectstd:
                        if desc in print_lines:
                            continue
                        if desc in std_lines:
                            continue
                else:
                    # out+err log file
                    if not redirectstdout:
                        if desc in print_lines:
                            continue
                        if desc in std_out_lines:
                            continue
                    if not redirectstderr:
                        if desc in std_err_lines:
                            continue
            else:
                # expected stdout/stderr content
                if not std:
                    if redirectstd:
                        continue
                    if desc in lines_need_logger:
                        continue
            if level_filtered(level, desc):
                # Log level too high
                continue
            msg = prefix + msg
        else:
            # expected stdout/stderr content
            if desc in lines_need_logger:
                continue
            # No logger formatting so no prefix
        lines.append(msg)
    if lines:
        lines.append("")
    return lines


def level_filtered(level, desc):
    levels = log_levels
    if desc in levels:
        return desc not in levels[levels.index(level) :]
    else:
        return False


def expected_stdout(stdout=None, redirectstdout=None, **kwargs):
    return expected_std(outtype="out", std=stdout, redirectstd=redirectstdout, **kwargs)


def expected_stderr(stderr=None, redirectstderr=None, **kwargs):
    return expected_std(outtype="err", std=stderr, redirectstd=redirectstderr, **kwargs)


def expected_file(
    logfile=None,
    outtype=None,
    createlogger=None,
    stdout=None,
    stderr=None,
    redirectstdout=None,
    redirectstderr=None,
    **kwargs,
):
    if logfile and createlogger:
        if outtype == "out":
            std = stdout
            redirectstd = redirectstdout
        elif outtype == "err":
            std = stderr
            redirectstd = redirectstderr
        else:
            std = stdout, stderr
            redirectstd = redirectstdout, redirectstderr
        return expected_std(
            outtype=outtype,
            createlogger=createlogger,
            file=True,
            std=std,
            redirectstd=redirectstd,
            **kwargs,
        )
    else:
        return []


def expected_fileout(fileout=None, **kwargs):
    return expected_file(outtype="out", logfile=fileout, **kwargs)


def expected_fileerr(fileerr=None, **kwargs):
    return expected_file(outtype="err", logfile=fileerr, **kwargs)


def validate_output(tmpdir, output, outtype, **kwargs):
    if outtype == "stdout":
        lines = expected_stdout(**kwargs)
    elif outtype == "stderr":
        lines = expected_stderr(**kwargs)
    elif outtype == "fileout":
        lines = expected_fileout(**kwargs)
    elif outtype == "fileerr":
        lines = expected_fileerr(**kwargs)
    elif outtype == "fileall":
        return  # TODO
        lines = expected_file(**kwargs)
    lines = os.linesep.join(lines)
    args = [codefilename(tmpdir)] * lines.count("{}")
    lines = lines.format(*args)
    lines = lines.split(os.linesep)
    output = output.split(os.linesep)
    timestamp = r" \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} "
    output = [re.sub(timestamp, ":", s) for s in output]

    if lines != output:
        cmd = " ".join(cliargs(tmpdir, **kwargs))
        errmsg = "Unexpected {}".format(repr(outtype))
        errmsg += "\n Command: {}".format(repr(cmd))
        errmsg += "\n\n Options: {}".format(pprint.pformat(kwargs, indent=2))
        errmsg += "\n\n Difference (-: missing, +: unexpected)"
        errmsg += "\n " + "\n ".join(differ.compare(lines, output))
        raise RuntimeError(errmsg)


def cliargs(
    tmpdir,
    level=None,
    fileall=None,
    fileout=None,
    fileerr=None,
    stdout=None,
    stderr=None,
    redirectstdout=None,
    redirectstderr=None,
    **kwargs,
):
    filename = codefilename(tmpdir)
    args = ["python", filename, "--log=" + level]
    if fileall:
        args.append("--logfile={}".format(allfilename(tmpdir)))
    if fileout:
        args.append("--logfileout={}".format(outfilename(tmpdir)))
    if fileerr:
        args.append("--logfileerr={}".format(errfilename(tmpdir)))
    if not stdout:
        args.append("--nologstdout")
    if not stderr:
        args.append("--nologstderr")
    if redirectstdout:
        args.append("--redirectstdout")
    if redirectstderr:
        args.append("--redirectstderr")
    return args


def remove_log_files(tmpdir):
    filenames = [outfilename(tmpdir), errfilename(tmpdir), allfilename(tmpdir)]
    for filename in filenames:
        try:
            os.remove(filename)
        except FileNotFoundError:
            pass


def generate_output(tmpdir, **kwargs):
    remove_log_files(tmpdir)
    lst = cliargs(tmpdir, **kwargs)
    p = subprocess.Popen(lst, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    fileall, fileout, fileerr = read_files(tmpdir)
    return {
        "stdout": stdout.decode(),
        "stderr": stderr.decode(),
        "fileall": fileall,
        "fileout": fileout,
        "fileerr": fileerr,
    }


def run_test(tmpdir, createlogger=None):
    choices = {
        "createlogger": (createlogger,),
        "level": log_levels,
        "fileout": (False, True),
        "fileerr": (False, True),
        "fileall": (False, True),
        "stdout": (False, True),
        "stderr": (True,),
        "redirectstdout": (False, True),
        "redirectstderr": (False, True),
    }
    parameters = list(choices.keys())
    values = list(choices.values())
    for values in itertools.product(*values):
        kwargs = dict(zip(parameters, values))
        generate_test_script(tmpdir, **kwargs)
        result = generate_output(tmpdir, **kwargs)
        for outtype, output in result.items():
            validate_output(tmpdir, output, outtype, **kwargs)


def test_systemlogging(tmpdir):
    run_test(tmpdir, createlogger=False)


def test_logging(tmpdir):
    run_test(tmpdir, createlogger=True)
