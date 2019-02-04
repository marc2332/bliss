## Configuring a PI piezo controller

This chapter explains how to configure a piezo controller from
Physical Instrument company.

This configuration should be common to the following models:

* PI E-753 - 754
* PI E-517 - 518
* PI E-712


### YAML configuration file example

    -
      controller:
        class: PI_E753
        tcp:
           url: e754id21-m0
        encoders:
          - name: e754m0_enc
            steps_per_unit: 1
            tolerance: 0.1
        axes:
            - acceleration: 1.0
              backlash: 0
              high_limit: null
              low_limit: null
              name: e754m0
              offset: 0
              encoder: e754m0_enc
              steps_per_unit: 1
              tolerance: 0.1
              velocity: 11
              tango_server: e754m0
