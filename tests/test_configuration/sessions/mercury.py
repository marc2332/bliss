from bliss import setup_globals


def run_gate(a=1., b=1., nb=100):
    o = setup_globals.opiom1
    o.comm_ack("CNT 1 RESET")
    args = int(a * 1000 * 2000), int(b * 1000 * 2000), int(nb)
    o.comm_ack("CNT 1 CLK2 PULSE {:d} {:d} {:d}".format(*args))
    o.comm_ack("CNT 1 START")
