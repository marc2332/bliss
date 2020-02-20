!!! info

    The objective of this example is not to  teach a specific alignment procedure for slits but rather to demonstrate how to the interaction with flint works and how to define offsets on motors.


The procedure presented below is based on the following main steps (of case there are other ways to align silts...):
1. define the 0 position of hardware motors at _half beam position_ to define gap = 0 
2. scan _slit_offset_ at small gap opening to find the 0 position of _slit_offset _

-  get a first image in flint to see slits are not aligned ... gap not closed even though _slit_vertical_gap = 0_

```python
DEMO_SESSION [1]: ct(.1,beamviewer)
```

-  open gap to large extend using the hardware motors

```python
DEMO_SESSION [2]: umv(slit_top,3,slit_bottom 3)       
```

- Aim of the next steps: align the hardware motors to the _half beam position_  to define slit_vertical_gap = 0

- scan top blade and align half beam position
 
```python
DEMO_SESSION [3]: ascan(slit_top,-2,2,20,.1,beamviewer) 
         Out [3]: Scan(number=4, name=ascan, path=/tmp/scans/demo_session/data.h5)
                                                                                                           
DEMO_SESSION [4]: cen(beamviewer.counters.roi1_sum)
DEMO_SESSION [5]: goto_cen(beamviewer.counters.roi1_sum)

DEMO_SESSION [6]: plotselect(beamviewer.counters.roi1_sum)

DEMO_SESSION [6]: goto_cen()

DEMO_SESSION [7]: slit_top.position=0
```

- now slit_top is aligned, move it out of the way and repeat the same procedure for slit_bottom

```python
DEMO_SESSION [9]: umv(slit_top,3)

DEMO_SESSION [10]: ascan(slit_bottom,-2,2,20,.1,beamviewer)

DEMO_SESSION [11]: goto_cen()

DEMO_SESSION [12]: slit_bottom.position=0
```

- now slit_bottom is aligned as well. Move both hardware motors to 0 postion which is equivalent of closed gap
- now setting slit_vertical_gap = 0 in this position

```python
DEMO_SESSION [13]: umv(slit_top,0)
                                                                                                                       
DEMO_SESSION [14]: loopscan(1,.1,beamviewer)
         Out [14]: Scan(number=6, name=loopscan, path=/tmp/scans/demo_session/data.h5) 
                                                                                                                                 
DEMO_SESSION [15]: wa()
Current Positions: user
                   dial                                                                                                          
                                                                                                                                 
     sy    sz[mm]    slit_top    slit_bottom    slit_vertical_gap    slit_vertical_offset
-------  --------  ----------  -------------  -------------------  ----------------------                                        
0.00000   0.00000     0.00000        0.00000              0.00000                 0.00000
0.00000   0.00000    -0.43800        0.05600              0.00000                 0.00000

DEMO_SESSION [16]: slit_vertical_gap.position = 0
```

- open gap a little bit to be able to scan the offset

```python
DEMO_SESSION [17]: umv(slit_vertical_gap, .1)

DEMO_SESSION [18]: ascan(slit_vertical_offset,-2,2,40,.1,beamviewer)

DEMO_SESSION [19]: goto_cen()

DEMO_SESSION [20]: wa()
Current Positions: user
                   dial                                                                                                          
                                                                                                                                 
     sy    sz[mm]    slit_top    slit_bottom    slit_vertical_gap    slit_vertical_offset
-------  --------  ----------  -------------  -------------------  ----------------------                        
0.00000   0.00000     0.07000        0.03000              0.10000                 0.02000
0.00000   0.00000    -0.36800        0.08600              0.10000                 0.02000
                                     
DEMO_SESSION [21]: slit_vertical_offset.position=0 
```

- now the slit (_slit_vertical_gap_ and _slit_vertical_offset_) should be aligned.


