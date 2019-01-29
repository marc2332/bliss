# New Focus Picomotor Controller configuration

## NF8753 and NF8752

### Yaml sample configuration

```YAML
  controller:
    class: NF8753
    host: newfocusid30a3
    axes:
        -   name: kbf_back
            driver: A1
            channel: 0
            steps_per_unit: 50
            velocity: 0.2
            acceleration: 0.75
            
        -   name: kbf_front
            driver: A1
            channel: 1
            steps_per_unit: 50
            velocity: 0.2
            acceleration: 0.75
```

## NF8742

### Yaml sample configuration

```YAML
  controller:
    class: NF8742
    host: newfocusid232.esrf.fr
    axes:
        -   name: bm2v1
            channel: 1
            steps_per_unit: 333.33
            velocity: 5
            acceleration: 0.1
            
        -   name: bm2v2
            channel: 2
            steps_per_unit: 333.33
            velocity: 5
            acceleration: 0.1

```
