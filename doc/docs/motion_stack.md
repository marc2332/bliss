# Stack motors

A `Stackmotor` consists in a pair of motors mounted on top of each other

- one motor with a large stroke (fast but not very precise)
- and one with a short stroke (slow but very precise)

A `Stackmotor` can be (de)activated with `stack_on` & `stack_off`.

- when inactive only the large motor will move when moving the stack
- when active, the small motor will make the move if it stays within its limits,
  otherwise the small motor is moved to its middle position and the large motor makes the move.

## Example configuration

Here is the corresponding *YAML* configuration for a stack named `mstack` (= m1 + m2).

```yaml
# stackmotor.yml

controller:
  - module: stackmotor
    class: StackMotor
    axes:
      # large stroke motor
      - name: $m1
        tags: real mls

      # small stroke motor
      - name: $m2
        tags: real mss
        # low and high limits
        low_limit: -1
        high_limit: 1
        # absolute limits:
        #   if False, limits are calculated from the current position when stack is enabled
        #   at startup stack is enabled
        absolute_limits: False

      - name: mstack
        tags: stack
        unit: mrad
```
