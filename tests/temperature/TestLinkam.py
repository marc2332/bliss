import sys
import time
from bliss.controllers.temperature.linkam import LinkamDsc

config = {
    "serial_url": "rfc2217://ld262:28068",  # serial line name
    "serial_baudrate": 19200,
    "max_temp": 910,
    "min_temp": -40,
}
dev = LinkamDsc("T95", config)
# for i in range(20):
#    time.sleep(1)
#    print dev.getTemperature()

# print dev.pumpSpeed
# dev.pumpSpeed = 0
# dev.rampRate = 10
# dev.rampLimit=25
# dev.rampHoldTime=5000
# dev.getTemperature()
# dev.stop()
# print dev.status()
# dev.start()
# print dev._profile_task
# dev.setTemperature(25)
# dev.cool()
dev.profile([(10, 35, 0)])
# dev.profile([(5,30,60),(5,35,30),(1,25,0)])
with open("rampData", "w") as f:
    while 1:
        time.sleep(0.1)
        temp, dsc = dev.getDscData()
        print "temp  ", temp, " dsc ", dsc
        #        print "rampNb",dev.rampNumber," rampLimit",dev.rampLimit," rampRate",dev.rampRate,"rampHold",dev.rampHoldTime
        f.write("%f %f\n" % (ts, temp))
        print dev.status()
        running = dev.isProfileRunning()
        print "Profile running ", running
        if running == False:
            break

# with open('temperatureData', 'w') as f:
#    while (1):
#        f.write("{0}\n".format(dev.getTemperature()))
#        time.sleep(5)
