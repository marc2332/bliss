# Lakeshore cryostat

## Configuration of ls336
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
Last alternative for the model 336 would be to use USB interface.

Other models (used at ESRF and fow which BLISS controller exists)
have the following possible interfaces:

model 331 can use RS232.
model 332 can use GPIB or RS232.
model 335 can use GPIB or USB.
model 340 can use GPIB or RS232.


