from bliss.config.static import get_config
from bliss.controllers.ct2.tango.client import CT2Device, AcqStatus

config = get_config()

p201_name = 'p201_lid312_0'

p201_dev = CT2Device(config, p201_name)
print "acq_channels=%s" % (p201_dev.acq_channels,)
print "timer_freq=%s" % p201_dev.timer_freq
print "counters=%s" % (p201_dev.counters,)
p201_dev.acq_expo_time = 20
p201_dev.acq_channels = (1, 3, 6)
p201_dev.prepare_acq()
p201_dev.start_acq()
while p201_dev.acq_status == AcqStatus.Running:
    print p201_dev.counters, p201_dev.acq_status
    import time
    time.sleep(0.1)
