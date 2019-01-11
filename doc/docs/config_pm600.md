## Configuring a PM600 motor controller

This section explains how to configure a McLennan PM600 motor controller.

    Example YAML configuration:

    .. code-block:: yaml
    
    controller:
      class: PM600
      tcp: 148.79.208.131:5000
      axes:
        -
            name: mono
            address: 1
            velocity: 5000.0
            acceleration: 10000.0
            deceleration: 10000.0
            creep_speed: 200.0
            steps_per_unit: 1
            soft_limit_enable: 1
            low_limit: -2000000000.0
            high_limit: 2000000000.0
            backlash: 0.01
            creep_steps: 1
            limit_decel: 2000000
            settling_time: 2
            window: 10
            threshold: 50
            tracking: 4000
            timeout: 30000
            Kf: 0
            Kp: 3500
            Ks: 0
            Kv: 0
            Kx: 10
            gearbox_ratio_numerator: 1
            gearbox_ratio_denominator: 1
            encoder_ratio_numerator: 7200
            encoder_ratio_denominator: 31488
    

