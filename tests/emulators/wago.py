import random
from collections import defaultdict
import logging
from socketserver import TCPServer
import threading

from umodbus import conf
from umodbus.server.tcp import RequestHandler, get_server
from umodbus.utils import log_to_stream

from bliss.controllers.wago.helpers import to_unsigned, bytestring_to_wordarray
from bliss.controllers.wago.wago import MODULES_CONFIG, _WagoController
from bliss.controllers.wago.helpers import remove_comments, splitlines


def Wago(address, slave_ids=list(range(1, 256)), modules=None, randomize_values=True):
    """
    Creates a synchronous modbus server serving 2 different memory areas
     * coils and inputs for boolean values
     * registers and holding for non boolean values

    Supported modbus functions are:
      * 1,2,3,4,5,6,15,16

    Args:
        modules (str): list of modules E.G. "750-469","750-517"
                       NOTE: the first one should be a CPU like "750-842"

    Example:
        >>> modules = "750-842 750-469 750-469 750-469 750-469 750-469 750-469 750-469 750-469 750-469 750-517 750-517 750-479"

        >>> Wago(("localhost", 34012), modules=modules.split(), randomize_values=True)
    """

    log_to_stream(level=logging.DEBUG)

    # Enable values to be signed (default is False).

    conf.SIGNED_VALUES = False

    def random_bit():
        return bool(random.getrandbits(1))

    def random_word():
        return random.randrange(65535)

    regs_io_boolean = defaultdict(random_bit)  # initialize at a random value

    regs_word = defaultdict(
        int
    )  # modbus input registers and holding registers shares the same area

    regs_io_words = defaultdict(
        random_word
    )  # modbus input registers and holding registers shares the same area

    regs_interlock = defaultdict(int)

    # helper functions
    def write_mem(start, data):
        for addr, reg in zip(range(start, start + len(data), data)):
            regs_word[addr] = reg

    def fit(bytestring: bytes, final_size):
        """ fits a bytestring to a given size"""
        extended = bytestring + (final_size - len(bytestring)) * b"\x00"
        trimmed = extended[:final_size]
        return trimmed

    TCPServer.allow_reuse_address = True
    TCPServer.timeout = .1
    app = get_server(TCPServer, address, RequestHandler)

    interlock_phase = 0

    # 0x2020 x 16H Short description controller

    # on reading 16 registers starting from 0x2021 we get this kind of response
    # b'10:50:39\x00\x00\x00\x00\x00\x00\x00\x0017:37:27\x00\x00\x00\x00\x00\x00\x00\x00'
    # that contains the time

    # 0x2022 x 8H Compiler date of firmware
    # 0x2023 x 32H Indication of the firmware loader
    # b'Programmed by ELECTRONICC Production in Minden\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'

    # on reading 16 registers starting from 0x2022 we get this kind of response
    # b'Jan  3 2014\x00\x00\x00\x00\x002017-10-09\x00\x00\x00\x00\x00\x00'

    # Connected modules READ ONLY
    # 0x2030 x 65H Description of the connected I/O modules (0..64)
    # 0x2031 x 64H Description of the connected I/O modules (65..128)
    # 0x2032 x 64H Description of the connected I/O modules (129..192)
    # 0x2033 x 63H Description of the connected I/O modules (193..255)

    # constants
    regs_word[0x2000] = 0
    regs_word[0x2001] = 0xffff
    regs_word[0x2002] = 0x1234
    regs_word[0x2003] = 0xaaaa
    regs_word[0x2004] = 0x5555
    regs_word[0x2005] = 0x7fff
    regs_word[0x2006] = 0x8000
    regs_word[0x2007] = 0x3fff
    regs_word[0x2008] = 0x4000

    # info READ ONLY
    regs_word[0x2010] = 19  # firmware version
    regs_word[0x2011] = 750  # PLC Seris
    regs_word[0x2012] = 842  # Coupler/controller code
    regs_word[0x2013] = 255  # Firmware version major revision
    regs_word[0x2014] = 255  # Firmware version minor revision

    @app.route(
        slave_ids=slave_ids,
        function_codes=[3, 4],
        addresses=list(regs_word.keys()),
        quantity=[1],
    )
    def const_and_info(slave_id, function_code, address):
        return regs_word[address]

    @app.route(
        slave_ids=slave_ids,
        function_codes=[3, 4],
        addresses=list(range(0x2020, 0x2020 + 16)),
    )
    def short_description(slave_id, function_code, address):
        short_descr = bytestring_to_wordarray(fit(b"WAGO-Ethernet TCP/IP PFC", 16 * 2))
        return short_descr[address - 0x2020]

    # 0x2021 x 8H Compiler time of firmware
    @app.route(
        slave_ids=slave_ids,
        function_codes=[3, 4],
        addresses=list(range(0x2021, 0x2021 + 8)),
        starting_address=0x2021,
    )
    def compile_time(slave_id, function_code, address):
        series = bytestring_to_wordarray(fit(b"10:50:39", 8 * 2))
        return series[address - 0x2021]

    @app.route(
        slave_ids=slave_ids,
        function_codes=[3, 4],
        addresses=list(range(0x2022, 0x2022 + 8)),
        starting_address=0x2022,
    )
    def compile_date(slave_id, function_code, address):
        date = bytestring_to_wordarray(fit(b"Jan  3 2014", 8 * 2))
        return date[address - 0x2022]

    @app.route(
        slave_ids=slave_ids,
        function_codes=[3, 4],
        addresses=list(range(0x2023, 0x2023 + 32)),
        starting_address=0x2023,
    )
    def firmware_loaded(slave_id, function_code, address):
        firmware = bytestring_to_wordarray(
            fit(b"Programmed by ELECTRONICC Production in Minden", 32 * 2)
        )
        return firmware[address - 0x2023]

    # Connected modules READ ONLY
    # 0x2030 x 65H Description of the connected I/O modules (0..64)
    # 0x2031 x 64H Description of the connected I/O modules (65..128)
    # 0x2032 x 64H Description of the connected I/O modules (129..192)
    # 0x2033 x 63H Description of the connected I/O modules (193..255)

    @app.route(
        slave_ids=slave_ids,
        function_codes=[3, 4],
        addresses=list(range(0x2030, 0x2030 + 65)),
        starting_address=0x2030,
    )
    def connected_IO_modules(slave_id, function_code, address):
        """
        Description of the connected I/O modules
        returns 1 word per module

        These 65 registers identify the controller and the first 64 modules present in a
        node. Each module is represented in a word. Because order numbers cannot be
        read out of digital modules, a code is displayed for them, as defined below:
            Bit position 0 -> Input module
            Bit position 1 -> Output module
            Bit position 2...7 -> Not used
            Bit position 8...14 -> Module size in bits
            Bit position 15 -> Designation digital module

        for non digital modules the returned value is the one that coresponds to the
        model of device, E.G. 750-469 will give 469
        """
        io_info = []  # assuming no attached module
        for i, module in enumerate(modules):
            if not i:
                # the first module is
                io_info.append(int(module.split("-")[1]))
                continue
            if module not in MODULES_CONFIG:
                raise RuntimeError(f"Can't find module '{module}'")
            module_info = MODULES_CONFIG[module]
            isdigital = bool(module_info[0] or module_info[1])
            isanalog = bool(module_info[2] or module_info[3])
            if isdigital and isanalog or not isdigital and not isanalog:
                raise RuntimeError(
                    "Wago couldn't have both digital and analog I/O in the same module"
                )
            isinput = bool(module_info[0] or module_info[2])
            isoutput = bool(module_info[1] or module_info[3])
            if isinput and isoutput or not isinput and not isoutput:
                raise RuntimeError(
                    "Wago couldn't have both input and output I/O in the same module"
                )
            size = module_info[4]
            if isdigital:
                io_info.append(
                    isinput | (isoutput << 1) | (size << 8) | (isdigital << 15)
                )
            else:
                io_info.append(int(module.split("-")[1]))
        while len(io_info) < 65:
            io_info.append(0)
        return to_unsigned(io_info[address - 0x2030])

    ################ INTERLOCK ###################3
    @app.route(
        slave_ids=slave_ids,
        function_codes=[6, 16],  # check
        addresses=[0x100],
        starting_address=0x100,
        quantity=[1],
    )
    def interlock_handshake_phase_1(
        slave_id, function_code, address, value, starting_address, quantity
    ):
        print("phase 1")
        if value == 0:
            regs_interlock = defaultdict(int)  # empty memory
            phase = 2
            # next_step

    @app.route(
        slave_ids=slave_ids,
        function_codes=[4],  # check if also fc 3 works
        addresses=list(range(0x100, 0x100 + 126)),
        starting_address=0x100,
        quantity=[2, 126],
    )
    def interlock_handshake_read(
        slave_id, function_code, address, starting_address, quantity
    ):
        if phase == 2:
            # PHASE 2: Handshake protocol: wait for OUTCMD==0
            print("phase 2")
            msg = [0xaa01, 0, 0]
            regs_interlock = defaultdict(int)  # resets memory for next command
            phase = 3
            return msg[address - 0x100]

        if phase == 4:
            #
            #  Evaluate the command
            #
            error_code = 0
            command_executed = regs_interlock[0x101]
            registers_to_read = 1
            msg = [0xaa01, error_code, command_executed, registers_to_read]
            phase = 5
            return msg[address - 0x100]
            # elaborate
        if phase == 5:
            msg = [0, 0]  # to do response
            phase = 0
            return msg[address - 0x104]

    @app.route(
        slave_ids=slave_ids,
        function_codes=[16],  # check
        addresses=list(range(0x100, 0x100 + 126)),
        starting_address=0x100,
        quantity=list(range(2, 126)),
    )
    def interlock_handshake_write(
        slave_id, function_code, address, value, starting_address, quantity
    ):
        # regs_word[address] = value

        if phase == 3:
            # PHASE 3: Handshake protocol: write the command to process and its parameters
            regs_interlock[address] = value

            if address - starting_address == quantity - 1:  # last write
                # next step
                phase = 4
            if address == 0x101:
                assert value == 0xa5a5

            return msg[address - 0x100]
        """
        print("phase 3")
        print(address, starting_address, quantity)
        if address - starting_address == quantity -1:
            # we are at the last register, we suppose that writing is finish
            print("finished request")
            # prepare response
            error_code = 0
            command_executed = regs_word[0x100]  # just executed command
            reg_to_read = 1
            # prepare phase 4
            write_mem(0x100, (0xaa01, error_code, command_executed, reg_to_read))
            print(f"command executed {command_executed} reg_to_read {reg_to_read}")
        """

        # trigger response

    ###### DIGITAL IN/OUT ######

    # First 512 digital inputs
    @app.route(
        slave_ids=slave_ids, function_codes=[1, 2], addresses=list(range(0, 512))
    )
    def first_512_inputs_read(slave_id, function_code, address):
        if randomize_values:
            return bool(random.getrandbits(1))
        else:
            return regs_io_boolean[address]

    # First 512 digital outputs
    @app.route(
        slave_ids=slave_ids, function_codes=[1, 2], addresses=list(range(512, 1024))
    )
    def first_512_outputs_read(slave_id, function_code, address):
        if randomize_values:
            return bool(random.getrandbits(1))
        else:
            return regs_io_boolean[address]

    @app.route(
        slave_ids=slave_ids, function_codes=[5, 15], addresses=list(range(0, 1024))
    )
    def first_512_outputs_write(slave_id, function_code, address, value):
        if address > 511:
            # registers starting at 512 are a duplication
            address -= 512
        if randomize_values:
            return bool(random.getrandbits(1))
        else:
            return regs_io_boolean[address]

    ###### ANALOG IN/OUT ######

    @app.route(
        slave_ids=slave_ids, function_codes=[3, 4], addresses=list(range(0, 256))
    )
    def physical_input_area(slave_id, function_code, address):
        if randomize_values:
            return random.randrange(65535)
        else:
            return regs_io_words[address]

    # First 512 digital outputs
    @app.route(
        slave_ids=slave_ids, function_codes=[3, 4], addresses=list(range(512, 768))
    )
    def physical_output_area_read(slave_id, function_code, address):
        if randomize_values:
            return random.randrange(65535)
        else:
            return regs_io_words[address - 512]

    @app.route(
        slave_ids=slave_ids,
        function_codes=[6, 16],
        addresses=list(range(0, 256)) + list(range(512, 768)),
    )
    def physical_output_area_write(slave_id, function_code, address, value):
        if address > 511:
            # registers starting at 512 are a duplication
            address -= 512
        if randomize_values:
            return random.randrange(65535)
        else:
            return regs_io_words[address - 512]

    t = threading.currentThread()

    try:
        while getattr(t, "do_run", True):  # handles until a signal from parent thread
            app.handle_request()
    finally:
        app.server_close()
