

# TangoShutter

`TangoShutter` class is used to control (via Tango Device Server):

* frontend
* safety shutter
* vaccum remote valves

Some commands/attributes (like automatic/manual) are only implemented in the
front end device server, set by the `_frontend` variable.


## example

```yaml
-
  name: safshut
  class: TangoShutter
  uri: id42/bsh/1

-
  # front end shutter
  class: TangoShutter
  name: frontend
  uri: //orion:10000/fe/master/id42

```

```yaml
-
  name: rv0
  class: TangoShutter
  uri: id42/v-rv/0
-
  name: rv1
  class: TangoShutter
  uri: id42/v-rv/1
-
  name: rv2
  class: TangoShutter
  uri: id42/v-rv/2


```

