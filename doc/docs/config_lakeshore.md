# Lakeshore cryostat

## Configuration of ls330, ls332, and ls336
for connection via gpib
```YAML
        - class: lakeshore336
          plugin: temperature
          module: lakeshore.lakeshore336
          model: 336
          gpib:
              url: enet://gpibid03c.esrf.fr
              pad: 7
          outputs:
            - name: ls336Gsp
              channel: 1
          inputs:
            - name: ls336Gt
              channel: A
```

for connection via tcp
```YAML
        - class: lakeshore336
          plugin: temperature
          module: lakeshore.lakeshore336
          model: 336
          tcp:
            url: lakeshore336se1:7777
          outputs:
            - name: ls336Gsp
              channel: 1
          inputs:
            - name: ls336Gt
              channel: A
```

Note that ls335 is treated differently in bliss.
