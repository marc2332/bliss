import sys
import time
from bliss.controllers.temperature.linkam import LinkamDsc

config = {"tcp_url": "socket://148.79.215.54:5678", "max_temp": 900, "min_temp": -30}
# dev=LinkamDsc(config)

config = {
    "serial_url": "/dev/tty",
    "serial_baudrate": 19200,
    "max_temp": 910,
    "min_temp": -40,
}
dev = LinkamDsc(config)
print("starting ramp is: ", dev.startingRamp)
dev.startingRamp = 4
print("starting ramp is: ", dev.startingRamp)
print("state ", dev.state)
# print dev.dscSamplingRate
# dev.dscSamplingRate = 0.7
# print dev.dscSamplingRate
# print dev.pumpSpeed
# dev.pumpSpeed = 30
# print dev.pumpSpeed
# dev.setPumpAutomatic()
# dev.setPumpManual()
dev.startingRamp = 2
for i in range(5):
    dev.profile([(1, 2, 3), (4, 5, 6)])
    time.sleep(4)
    dev.setStatusString("2000003a980000")
    time.sleep(2)
    for j in range(25):
        time.sleep(0.5)
        print(j, dev.getDscData())
    time.sleep(2)
    dev.setStatusString("3000003a980000")
    time.sleep(2)
    dev.setStatusString("1000003a980000")
    time.sleep(2)
    dev.setStatusString("2000003a980000")
    time.sleep(1)
    if i == 2:
        dev.setStatusString("2100003a980000")
        dev.stop()
        time.sleep(2)
        break
    time.sleep(3)
    dev.setStatusString("3000003a980000")
    time.sleep(5)
    dev.setStatusString("1000003a980000")
    time.sleep(5)
