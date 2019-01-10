# Keithley configuration


### Configuration


        plugin: keithley
        keithleys:
          - name: k_ctrl_6
            class: Ammeter
            model: 6485
            auto_zero: False
            display: False
            zero_check: False
            zero_correct: False
            gpib:
              url: enet://gpibid11c.esrf.fr
              pad: 22
            sensors:
              - name: pico6
                address: 1
                current_dc_nplc: 0.1
                current_dc_auto_range: True

          - name: k_ctrl_7
            class: Ammeter
            model: 6485
            auto_zero: False
            display: False
            zero_check: False
            zero_correct: False
            gpib:
              url: enet://gpibid11c.esrf.fr
              pad: 23
            sensors:
              - name: pico7
                address: 1
                current_dc_nplc: 0.1
                current_dc_auto_range: True
