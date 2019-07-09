# Keithley configuration


### Configuration

#### Minimum

        plugin: keithley
        keithleys:
          - model: 2000
            gpib:
              url: enet://gpibid11c.esrf.fr
              pad: 22
            sensors:
              - name: pico6
	        meas_func: VOLT
                address: 1

          - model: 6485
            gpib:
              url: enet://gpibid11c.esrf.fr
              pad: 23
            sensors:
              - name: pico7
                address: 1

#### Full

        plugin: keithley
        keithleys:
          - model: 6485
            auto_zero: False
            display: False
            gpib:
              url: enet://gpibid11c.esrf.fr
              pad: 22
            sensors:
              - name: pico6
                address: 1
                nplc: 0.1
                auto_range: False
		range: 2e-8
                zero_check: False
                zero_correct: False


