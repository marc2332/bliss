# Eurotherm configuration

## Example Configuration

    - class: eurotherm2000
      serial: 
        url: "rfc2217://lid032:28008"
      inputs:
        - name: T
          type: pv 
      outputs:
        - name: sp
          resolution: full
          unit: deg
          low_limit: 0
          high_limit: 300
          deadband: 0.1

Aboves example worked on rocketport serial line made available via ser2net using the follwing parameters in ser2net.conf:

    28008:telnet:0:/dev/ttyR6:9600 remctl banner kickolduser

For a direct connection to a serial line the first lines of the configuration look as follows:

    - class: eurotherm2000
      serial:
        url: "/dev/ttyRP9"

