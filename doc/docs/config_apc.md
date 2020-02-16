# APC Rack Power Distribution Unit

Manifacturer: Schneider Electric

## Description

It is a Rack power plug with monitoring/automation capabilities
This implementation will put in place a Telnet connection and
send/receive commands.

What is implemented:

- switch on and off of a power outlet

## YAML Configuration example

```YAML
plugin: bliss
module: apc
class: APC
name: apc
host: apchostname
debug: True  # will print to stdout telnet handshake
user: apc
password: apc
timeout: 1
channels:
  - laser
  - led
```

For every given channel two methods will be added to the
instance ending with `on` and `off`.

In the given case we will have:

- laseron
- laseroff
- ledon
- ledoff
