# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent

from .opiom import Opiom
from bliss.config import static
from bliss.config.settings import HashObjSetting


class Output:
    class Node:
        def __init__(self, board, register, shift, mask, value, parentNode):
            self.__board = board
            self.__register = register.upper()
            shift = shift
            self.__mask = mask << shift
            self.__value = value << shift
            self.__parent = parentNode

        def switch(self, synchronous):
            if self.__parent:
                self.__parent.switch(False)

            op = self.__board
            cmd = "%s 0x%x 0x%x" % (self.__register, self.__value, self.__mask)
            if synchronous:
                op.comm_ack(cmd)
            else:
                op.comm(cmd)

        def isActive(self, opiom_registers):
            activeFlag = True
            if self.__parent:
                activeFlag = self.__parent.isActive(opiom_registers)

            registerValue = opiom_registers[self.__board][self.__register]
            return activeFlag and ((registerValue & self.__mask) == self.__value)

    def __init__(self, multiplex, config_dict):
        config = dict(config_dict)

        self.__multiplex = multiplex
        self.__name = config.pop("label").upper()
        self.__comment = config.pop("comment", "")
        self.__nodes = dict()

        self.__build_values(config)

    def name(self):
        return self.__name

    def comment(self):
        return self.__comment

    def getSwitchList(self):
        return list(self.__nodes.keys())

    def switch(self, switchValue, synchronous):
        switchValue = switchValue.upper()
        try:
            node = self.__nodes[switchValue]
        except KeyError:
            raise ValueError(switchValue)

        node.switch(synchronous)

    def getStat(self, opiom_register):
        for key, node in self.__nodes.items():
            if node.isActive(opiom_register):
                return key

    def __build_values(self, config, parentNode=None):
        cfg = dict()
        for key in ("board", "register", "shift", "mask"):
            value = config.pop(key, None)
            if value is None:
                raise RuntimeError(
                    "multiplexer: doesn't have '%s' keyword defined for %s switch"
                    % (key, self.__comment or self.__name)
                )
            cfg[key] = value

        board = self.__multiplex._boards.get(cfg["board"])
        if board is None:
            raise RuntimeError(
                "multiplexer: can't find the board %s in config" % cfg["board"]
            )

        register = cfg["register"]
        shift = cfg["shift"]
        mask = cfg["mask"]
        chain = config.pop("chain", None)  # check if chained

        for key, value in config.items():
            key = key.upper()
            self.__nodes[key] = Output.Node(
                board, register, shift, mask, value, parentNode
            )

        if chain is not None:
            value = chain.pop("chained_value")
            parentNode = Output.Node(board, register, shift, mask, value, parentNode)
            self.__build_values(chain, parentNode)


class Multiplexer:
    def __init__(self, name, config_tree):
        self.name = name
        self._boards = dict()
        self.__outputs = dict()

        all_config = static.get_config()

        for board in config_tree["boards"]:
            if hasattr(board, "name"):
                self._boards[board.name] = board
            else:
                board_name = board.get("name")
                self._boards[board_name] = all_config.get(board_name)

        for output_config in config_tree["outputs"]:
            output = Output(self, output_config)
            out = self.__outputs.setdefault(output.name(), output)
            if out != output:
                raise ValueError("Multiple output with the same name (%s)" % out.name())

        self.__stat = HashObjSetting("multiplexer.%s" % name)
        self.__debug = False

    def setDebug(self, flag):
        self.__debug = flag is True
        for opiom in self._boards.values():
            opiom.setDebug(self.__debug)

    def getDebug(self):
        return self.__debug

    def getOutputList(self):
        return list(self.__outputs.keys())

    def getPossibleValues(self, output_key):
        output_key = output_key.upper()
        return self.__outputs[output_key].getSwitchList()

    def getKeyAndName(self):
        return dict([(key, output.comment()) for key, output in self.__outputs.items()])

    def getName(self, output_key):
        output_key = output_key.upper()
        return self.__outputs[output_key].comment()

    def switch(self, output_key, input_key, synchronous=False):
        output_key = output_key.upper()
        input_key = input_key.upper()
        if self.__debug:
            print("Multiplexer.switch %s to %s" % (output_key, input_key))
        try:
            output = self.__outputs[output_key]
        except KeyError:
            raise ValueError("Multiplexer don't have the ouput %s" % output_key)
        else:
            try:
                output.switch(input_key, synchronous)
            except ValueError as err:
                raise ValueError(
                    "%s is not available for output %s" % (str(err), output_key)
                )

    def raw_com(self, message, board_name=None, synchronous=False):
        if board_name is None:  # take the first name in list
            if not len(self._boards):
                raise RuntimeError(
                    "multiplexer: no board defined for multiplexer (%s)" % self.name
                )
            board_name = list(self._boards.keys())[0]

        try:
            opiom = self._boards[board_name]
        except KeyError:
            raise ValueError(
                "Multiplexer don't have any board with this name (%s)" % board_name
            )

        if synchronous:
            return opiom.comm_ack(message)
        else:
            return opiom.comm(message)

    def getOutputStat(self, output_key):
        output_key = output_key.upper()
        if self.__debug:
            print("Multiplexer.getOutputStat %s" % output_key)
        output = self.__outputs[output_key]
        opiomRegister = {}
        futures = [(b, gevent.spawn(b.registers)) for b in self._boards.values()]
        for board, registers in futures:
            opiomRegister[board] = registers.get()

        return output.getStat(opiomRegister)

    def storeCurrentStat(self, name):
        opiomRegister = {}
        futures = [(b, gevent.spawn(b.registers)) for b in self._boards.values()]
        for board, registers in futures:
            opiomRegister[board.name] = registers.get()

        self.__stat[name] = opiomRegister

    def restoreStat(self, name):
        try:
            opiomRegister = self.__stat[name]
        except KeyError:
            raise ValueError("Multiplexer don't have the stat %s" % name)

        for board_name, reg in opiomRegister.items():
            for regName, value in reg.items():
                self._boards[board_name].comm("%s 0x%x" % (regName, value))

    def rmStat(self, name):
        try:
            self.__stat.pop(name)
        except KeyError:
            raise ValueError("Multiplexer don't have the stat %s" % name)

    def getSavedStats(self):
        return list(self.__stat.keys())

    def getGlobalStat(self):
        if self.__debug:
            print("Multiplexer.getGlobalStat")
        opiomRegister = {}
        futures = [(b, gevent.spawn(b.registers)) for b in self._boards.values()]
        for board, registers in futures:
            opiomRegister[board] = registers.get()
        outputStat = dict()
        for key, output in self.__outputs.items():
            outputStat[key] = output.getStat(opiomRegister)
        return outputStat

    def load_program(self):
        futures = [gevent.spawn(b.load_program) for b in self._boards.values()]
        gevent.joinall(futures)

    def getOpiomProg(self):
        progs = {}
        for opiomId, comm in self._boards.items():
            progs[opiomId] = comm.prog()
        return progs

    def dumpOpiomSource(self, board_name=None, all_board=True):
        if all_board:
            boards = self._boards.values()
        elif board_name is None:  # take the first name in list
            if not len(self._boards):
                raise RuntimeError(
                    "multiplexer: no board defined for multiplexer (%s)" % self.name
                )
            boards = [list(self._boards.values())[0]]
        else:
            try:
                boards = [self._boards[board_name]]
            except KeyError:
                raise ValueError(
                    "Multiplexer don't have any board with this name (%s)" % board_name
                )

        for board, source in ((b, gevent.spawn(b.source)) for b in boards):
            print("OPIOMID:", board.name)
            print("Prog.Source:")
            print(source.get())
            print("End of Prog.Source.")

    def __repr__(self):
        rep_str = "Multiplexer Status:\n\n"
        format = "{:<32}{:<32}\n"
        rep_str += format.format("Output name", "Output status")
        rep_str += "\n"
        for key, value in self.getGlobalStat().items():
            rep_str += format.format(key, value)
        return rep_str
