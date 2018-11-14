import socket
import time
import gevent


class UnknownDM:
    pass


def busy_state(f):
    def wrapper(self, *args, **kwargs):
        try:
            self._state = "MOVING"
            return f(self, *args, **kwargs)
        finally:
            self._state = "READY"

    return wrapper


class DmReader(object):
    def __init__(self, name, config):
        self.controller_ip = config.get("controller_ip")
        self.port = int(config.get("port", 8500))
        self.raw_data = [[None] * 11] * 3
        self._state = "READY"

    def connect(self, timeout=20):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect((self.controller_ip, self.port))
            # DN to start run mode
            s.sendall("R0\r")
            s.recv(4)
        except:
            raise RuntimeError(
                "cannot connect to datamatrix reader (%s, %d)"
                % (self.controller_ip, self.port)
            )
        else:
            return s

    @property
    def state(self):
        return self._state

    def get_list(self):
        s = self.connect()

        s.sendall("TA\r")

        if s.recv(3) != "TA\r":
            raise RuntimeError(
                "Could not retrieve data matrices from Keyence controller"
            )

        data_list = ""

        while True:
            data_list += s.recv(1024)
            if data_list.endswith("\r"):
                return data_list[:-1].split(",")

    def set_prg(self, prg, crd=2):
        card, prog_nb = self.get_prg()
        if card == crd and prog_nb == prg:
            return
        cmd = "PW,2,%s" % prg
        s = self.connect()
        s.sendall("%s\r" % cmd)
        if s.recv(3) == "ER\r":
            data_list = ""
            while True:
                data_list += s.recv(1024)
                if data_list.endswith("\r"):
                    if data_list[:-1].split(",")[-1] == "03":
                        raise RuntimeError("Prog does not exist in Keyence controller")
                    elif data_list[:-1].split(",")[-1] == "22":
                        raise RuntimeError("Number or range of parameters is incorrect")
            raise RuntimeError("Could not set the program")

    def get_prg(self):
        cmd = "PR"
        s = self.connect()
        s.sendall("%s\r" % cmd)
        if s.recv(3) == "ER\r":
            data_list = ""
            while True:
                data_list += s.recv(1024)
                if data_list.endswith("\r"):
                    if data_list[:-1].split(",")[-1] == "22":
                        raise RuntimeError("Some unnecessary parameter is included")
        data_list = s.recv(1024)
        return list(map(int, data_list[:-1].split(",")))

    @busy_state
    def get_barcode(self, puck_number=0, read_puck_barcode=False):
        self.set_prg(1)
        puck = {1: 0, 2: 22, 3: 44}
        samples = {1: puck[1] + 12, 2: puck[2] + 12, 3: puck[3] + 12}
        n_barcodes = 10
        data = 22 * 3 * [None]

        if puck_number > 3:
            raise ValueError("Invalid puck number")

        def check_presence(puck_number):
            if puck_number == 0:
                return any((check_presence(1), check_presence(2), check_presence(3)))
            else:
                return bool(1 - int(self.raw_data[puck[puck_number]]))

        def get_sample_barcodes(puck_number):
            return data[samples[puck_number] : samples[puck_number] + n_barcodes]

        for i in range(3):
            self.raw_data = self.get_list()
            if not check_presence(puck_number):
                raise RuntimeError("No puck")
            # this is to accumulate good results in data list
            # (consecutive calls will append new data)
            for j, x in enumerate(self.raw_data):
                if x:
                    data[j] = self.raw_data[j]
            ##
            if puck_number == 0:
                if all(data):
                    break
            else:
                if all(data[samples[puck_number]]):
                    break

        def puck_barcodes(puck_number):
            # initialize with puck barcode as 1st element
            bc = [data[puck[puck_number] + 1] if read_puck_barcode else None]
            bc.extend(get_sample_barcodes(puck_number))
            return bc

        if puck_number:
            return puck_barcodes(puck_number)
        else:
            return (puck_barcodes(1), puck_barcodes(2), puck_barcodes(3))

    def wrt_exec_condition(self, condition):
        cmd = "EXW,%s" % condition
        s = self.connect()
        s.sendall("%s\r" % cmd)
        if s.recv(3) == "ER\r":
            data_list = ""
            while True:
                data_list += s.recv(1024)
                if data_list.endswith("\r"):
                    if data_list[:-1].split(",")[-1] == "22":
                        raise RuntimeError(
                            "The number or the range of the parameter is incorrect"
                        )
            raise RuntimeError("Could not execute condition")

    def read_exec_condition(self):
        cmd = "EXR"
        s = self.connect()
        s.sendall("%s\r" % cmd)
        if s.recv(3) == "ER\r":
            data_list = ""
            while True:
                data_list += s.recv(1024)
                if data_list.endswith("\r"):
                    if data_list[:-1].split(",")[-1] == "22":
                        raise RuntimeError("Some unnecessary parameter is included")
        data_list = s.recv(1024)
        return list(map(int, data_list[:-1].split(",")))

    def sample_is_present(self, puck_number, sample_number):
        self.set_prg(3)
        self.wrt_exec_condition(sample_number + (puck_number - 1) * 10)
        res = (None, None)
        with gevent.Timeout(10, RuntimeError("no sample detected")):
            previous_res = None
            for i in range(3):
                all_presence = self.get_list()

                if bool(1 - int(all_presence[(puck_number - 1) * 11])):
                    res = (
                        True,
                        bool(
                            1
                            - int(all_presence[sample_number + (puck_number - 1) * 11])
                        ),
                    )
                else:
                    res = (False, False)

                if previous_res is not None and res != previous_res:
                    res = (None, None)
                    continue
                previous_res = res
        return res

    def get_puck_barcodes(self):
        list = 3 * [None]
        self.set_prg(4)
        for i in range(5):
            data = self.get_list()
            for j, x in enumerate(data):
                if x:
                    list[j] = data[j]
        if not None in list:
            return list

        self.set_prg(5)
        for i in range(5):
            data = self.get_list()
            for j, x in enumerate(data):
                if x:
                    list[j] = data[j]
        return list

    def get_RotTrans(self):
        self.set_prg(2)
        Rot_Trans = self.get_list()
        return Rot_Trans
