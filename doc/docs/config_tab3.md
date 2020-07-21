

# Tripod

tab3 3-legs tables


`tab3.py` is a re-implementation of SPEC `tab3.mac`/`tab3_mh.mac` macros set.


Many geometries are pre-defined:

## 0 - standard

## 1 - side front leg

## 2 - ID22 mirror

## 3 - ID21 mirror

## 4 - ID20

## 5 - ID29 mirror

## 6 - ID30

## 7 - ???

## 8 - ID21 KB/ZPZ support

* `l1` and `l2` are the 2 back legs. `lf` is the front leg
* the angle between (`l1`-`l2`) and (`l1`-`lf`) is orthogonal
* `B` is the mildle of (`l1`-`l2`)
* `C` is the middle of (`l1`-`lf`)
* `YTilt` rotation axis pass by `B` and is parallel to (`l1`-`lf`)
* `XTilt` rotation axis paas by `C` and is parallel to (`l1`-`l2`)
* `Height` is defined by the intersection of the 2 rotation axes

Configuration example:
```yaml
controller:
  class: tab3
  d1: 150
  d2: 130
  d3: 65
  d4: 75
  geometry: 8
  axes:
      -
          name: $zpz1
          tags: real back1
      -
          name: $zpz3
          tags: real back2
      -
          name: $zpz2
          tags: real front
      -
          name: zpz
          tags: z
          low_limit:  5.0
          high_limit: 9.0
          unit: mm
      -
          name: zprx
          tags: xtilt
          low_limit: -2.0
          high_limit: 2.0
          unit: mrad
      -
          name: zpry
          tags: ytilt
          low_limit: -5.0
          high_limit: 0.2
          unit: mrad
```
