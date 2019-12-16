## Configuring a PM600 motor controller

This section explains how to configure a McLennan PM600 motor controller.

### Supported features

Encoder | Shutter | Trajectories
------- | ------- | ------------
NO	| NO      | YES  

###Example YAML configuration:

```yaml

    controller:
      class: PM600
      serial:
         url: "rfc2217://lid265:28240"
         baudrate: 9600
         parity: E
         bytesize: 7
      axes:
        - name: mono
          address: '1'
          steps_per_unit: 144000.0
          velocity: 0.41666666666667
          acceleration: 1.67
          deceleration: 1.67
          creep_speed: 2.78e-05
          backlash: -0.138
          high_limit: 60.0
          low_limit: 4.0
          soft_limit_enable: '1'
          low_steps: -2000000000
          high_steps: 2000000000
          creep_steps: '1'
          limit_decel: '2000000'
          settling_time: '2'
          window: '10'
          threshold: '50'
          tracking: '4000'
          timeout: '30000'
          Kf: '0'
          Kp: '3500'
          Ks: '0'
          Kv: '0'
          Kx: '10'
          gearbox_ratio_numerator: '1'
          gearbox_ratio_denominator: '1'
          encoder_ratio_numerator: '7200'
          encoder_ratio_denominator: '31488'
          trajectory_sequence_number: '2'
          trajectory_profile_number: '0'
          #trajectory_pre_xp: ['WP22222220']
          #trajectory_post_cp: ['DE5000','WE','WP11111111']
```

###Trajectories

the PM600 hardware can be programmed to execute sequence of commands, and series of relative moves (profile). A constant time interval between the profile points is set at the begining of a sequence, and the hardware controller will adapt its velocity on its own (constant velocity between points).
the PM600 bliss controller will build such a program from a PVT array. One can hook pre and post trajectory commands that will be included into the sequence:

```
   from bliss.physics import trajectory

   traj = trajectory.PointTrajectory()

   times    = numpy.linspace(0,duration,nintervals+1) # linear timescale compulsory
   energies = numpy.linspace(energy_start,energy_end,nintervals+1) 
   angles = energytoangle (energies)

   traj.build(times,{'PM600':angles-angles[0]})       

   myaxis_trajectory = axis.Trajectory (my_axis, traj.pvt['PM600'])

   #hook some specific PM600 actions to the trajectory 
   #note that those can also be put in the config YML.

   # write to output port before starting profile, to synchronize with other hardware
   pre_xp = ['WP22222220']
   #put back slew rate velocity after profile has been executed
   post_xp = ['SV{0}'.format(my_axis.slewrate*my_axis.steps_per_unit)] 

   my_axis.trajectory_pre_xp  = pre_xp
   my_axis.trajectory_post_xp = post_xp

   return myaxis_trajectory
```   


####Some Special PM600 methods for trajectories

shows the profile and the sequence loaded into the PM600 controller
```
   myaxis.controller.trajectory_list(myaxis_trajectory)
```
saves profile and sequence into PM600 non-volatile flash memory so that they can be restored at power-up
```
   myaxis.controller.trajectory_backup(myaxis_trajectory)
   
```


