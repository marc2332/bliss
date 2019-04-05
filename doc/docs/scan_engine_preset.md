*Preset* are use to set environnement for a scan. Basically to control
opening/closing shutter, detector cover, multiplexer, scan pause...
It's a hook in scan iteration. This hook can be set in different level
for different need. Either the need is to hook a whole scan with an inherited class of
`ScanPreset` or the need is to hook a part of the acquisition chain with a object inherited of
`ChainPreset`.

##ScanPreset
This is the simplest one. This one has 3 callback methods:

  - *prepare* called before all devices preparation
  - *start* called before all devices starting
  - *stop* called after all devices are stopped.
```
TEST_SESSION [1]: from bliss.scanning.scan import ScanPreset                    
TEST_SESSION [2]: class Preset(ScanPreset): 
             ...:     def prepare(self,scan): 
             ...:         print(f"Preparing scan {scan.name}\n") 
             ...:     def start(self,scan): 
             ...:         print(f"Starting scan {scan.name}") 
             ...:         print(f"Opening the shutter") 
             ...:     def stop(self,scan): 
             ...:         print(f"{scan.name} scan is stopped")                 
             ...:         print(f"Closing the shutter") 
TEST_SESSION [3]: p = Preset()                                                  
TEST_SESSION [4]: s = loopscan(2,0.1,diode,run=False)                           
TEST_SESSION [5]: s.add_preset(p)                                               
TEST_SESSION [6]: s.run()                                                       
Total 2 points, 0:00:00.200000 (motion: 0:00:00, count: 0:00:00.200000)

Scan 12 Wed Mar 13 11:06:11 2019 /tmp/scans/test_session/data.h5 test_session user = seb
loopscan 2 0.1

           #         dt[s]         diode
Preparing scan loopscan

Starting scan loopscan
Opening the shutter
           0             0      -40.2222
           1      0.104891      -9.11111
Took 0:00:09.830967 (estimation was for 0:00:00.200000)
loopscan scan is stopped
Closing the shutter
```

##ChainPreset

This hook is link to a top-master of the acquisition chain. So the
callback method will be called during *prepare*, *start* and *stop*
phase of this to top-master. It has exactly the same behaviour of the
`ScanPreset` if the chain has **only one** top-master.

i.e: In a loopscan the only one top master is a timer, so here is the
same simple example where you want to open a shutter at the beginning
of the scan and closing it at the end.

```
TEST_SESSION [1]: from bliss.scanning.chain import ChainPreset                  
TEST_SESSION [1]: class Preset(ChainPreset): 
             ...:     def prepare(self,acq_chain): 
             ...:         print("Preparing") 
             ...:     def start(self,acq_chain): 
             ...:         print("Starting, Opening the shutter")         
             ...:     def stop(self,acq_chain): 
             ...:         print("Stopped, closing the shutter")                
TEST_SESSION [1]: s = loopscan(2,0.1,diode,run=False)                           
TEST_SESSION [1]: p = Preset()                                                  
TEST_SESSION [1]: s.acq_chain.add_preset(p)
TEST_SESSION [1]: s.run()                                                       
Total 2 points, 0:00:00.200000 (motion: 0:00:00, count: 0:00:00.200000)

Scan 13 Wed Mar 13 11:54:08 2019 /tmp/scans/test_session/data.h5 test_session user = seb
loopscan 2 0.1

           #         dt[s]         diode
Preparing
Starting, Opening the shutter
           0             0       24.1111
           1      0.105099       1.22222
Stopped, closing the shutter

Took 0:00:36.189189 (estimation was for 0:00:00.200000)
```

##ChainIterationPreset

Use this object when you want to set a hook on each iteration of a
top-master. `ChainIterationPreset` is **yield** from `ChainPreset`
instance by *get_iterator* method. i.e here is an example where you want to
open/close the shutter for each point.

```python
TEST_SESSION [1]: class Preset(ChainPreset): 
             ...:     class Iterator(ChainIterationPreset): 
             ...:         def __init__(self,iteration_nb): 
             ...:             self.iteration = iteration_nb 
             ...:         def prepare(self): 
             ...:             print(f"Preparing iteration {self.iteration}") 
             ...:         def start(self): 
             ...:             print(f"Starting, Opening the shutter iter {self.iteration}")         
             ...:         def stop(self): 
             ...:             print(f"Stopped, closing the shutter, iter {self.iteration}") 
             ...:     def get_iterator(self,acq_chain): 
             ...:         iteration_nb = 0 
             ...:         while True: 
             ...:             yield Preset.Iterator(iteration_nb) 
             ...:             iteration_nb += 1
TEST_SESSION [2]: p = Preset()
TEST_SESSION [3]: s = loopscan(2,0.1,diode,run=False)
TEST_SESSION [4]: s.acq_chain.add_preset(p)
TEST_SESSION [5]: s.run()
Total 2 points, 0:00:00.200000 (motion: 0:00:00, count: 0:00:00.200000)

Scan 18 Wed Mar 13 14:15:40 2019 /tmp/scans/test_session/data.h5 test_session user = seb
loopscan 2 0.1

           #         dt[s]         diode
Preparing iteration 0
Starting, Opening the shutter iter 0
Stopped, closing the shutter, iter 0
Preparing iteration 1
Starting, Opening the shutter iter 1
           0             0       22.4444
           1       0.10728       13.5556
Stopped, closing the shutter, iter 1

Took 0:00:16.677241 (estimation was for 0:00:00.200000)
```

In this example, you can see that *data display* and the *chain
iteration* are executed by two separated greenlets and they are not
synchronised. This is not a problem but can be confusing if you think
that it's sequencial.

##To pause a scan

As `Preset` callbacks are executed synchronously they can easily pause
it, just by not returning imediatly from *prepare*, *start* or *stop*
callback methods.  If for example you need to pause a scan if there is
no beam, you just have to check in a loop the condition.
As an example, wait to start a scan if the beam is not present. 
```python
class Preset(ScanPreset):
    def __init__(self,diode,beam_trigger_value):
        self._diode = diode
        self._beam_trigger_value
	
    def prepare(self,scan):
        beam_value = self._diode.read()
        while beam_value < self._beam_trigger_value:
            print(f"Waiting for beam, read {beam_value} expect {self._beam_trigger_value}",end='\r')
            gevent.sleep(1)
            beam_value = self._diode.read()
```