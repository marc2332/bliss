

"""
Bliss controller fo 4-motors Q-Sys support table for transfocators.
(ID22 - ID28? ...)


m1 m2 m3 m4 : aliases for real motors
thetay : alias for calculated y rotation
thetaz : alias for calculated z rotation
ty : alias for calculated y translation
tz : alias for calculated z translation

d1 : half distance in x direction (in mm) between the two moving blocks.

POI : point of interest (rotation center)

NOTE : We are using orientation conventions used on Q-Sys document.


<---X---Z
        |
        |
        Y
        |
        |
        V

   M2                   M3
            POI
               X           <------------------------- BEAM

   M1          |        M4
    |          |
    |<---D1--->|


Example configuration (from ID22):
==================================
<config>
  <controller class="IcePAP">
    <host value="iceid221" />
    <libdebug value="1" />
    <axis name="tfm1">
      <address value="21" />
      <steps_per_unit value="100" />
      <backlash value="0.1" />
      <velocity value="6000" />
    </axis>
    <axis name="tfm2">
      <address value="22" />
      <steps_per_unit value="100" />
      <backlash value="0.1" />
      <velocity value="6000" />
    </axis>
    <axis name="tfm3">
      <address value="23" />
      <steps_per_unit value="100" />
      <backlash value="0.1" />
      <velocity value="6000" />
    </axis>
    <axis name="tfm4">
      <address value="24" />
      <steps_per_unit value="100" />
      <backlash value="0.1" />
      <velocity value="8000" />
    </axis>
  </controller>
  <controller class="trans4">
    <axis name="tfm1" tags="real m1" />
    <axis name="tfm2" tags="real m2" />
    <axis name="tfm3" tags="real m3" />
    <axis name="tfm4" tags="real m4" />
    <axis name="tfroty" tags="thetay" />
    <axis name="tfrotz" tags="thetaz" />
    <axis name="tfty"  tags="ty" />
    <axis name="tftz"  tags="tz" />
    <d1 value="180" />
  </controller>
</config>
"""

from bliss.controllers.motor import CalcController
import math

class trans4(CalcController):

    def __init__(self, *args, **kwargs):
        CalcController.__init__(self, *args, **kwargs)

        self.d1 = self.config.get("d1", float)


    def calc_from_real(self, positions_dict):
        d1 = self.d1
        m1 = positions_dict["m1"]
        m2 = positions_dict["m2"]
        m3 = positions_dict["m3"]
        m4 = positions_dict["m4"]

        ty = ((m3 - m4) - (m1 - m2)) / 4
        tz =  (m1 + m2 + m3 + m4) / 2
        thetay = ((m3 + m4) - (m1 + m2)) / (2 * d1)
        thetaz = ((m1 - m2) + (m3 - m4)) / (4 * d1)

        _virt_dict =  { "thetay" : thetay,
                        "thetaz" : thetaz,
                        "ty" : ty,
                        "tz" : tz }

        print _virt_dict

        return _virt_dict

    def calc_to_real(self, axis_tag, positions_dict):
        '''
        Returns real motors positions (as a dictionary) given virtual
        ones.
        '''

        d1 = self.d1
        ty = positions_dict["ty"]
        tz = positions_dict["tz"]
        thetay = positions_dict["thetay"]
        thetaz = positions_dict["thetaz"]



        m1 = 0.5 * tz  -  ty  +  d1 * thetaz  -  0.5 * d1 * thetay
        m2 = 0.5 * tz  +  ty  -  d1 * thetaz  -  0.5 * d1 * thetay
        m3 = 0.5 * tz  +  ty  +  d1 * thetaz  +  0.5 * d1 * thetay
        m4 = 0.5 * tz  -  ty  -  d1 * thetaz  +  0.5 * d1 * thetay

        _real_dict = { "m1": m1,
                       "m2": m2,
                       "m3": m3,
                       "m4": m4 }

        print _real_dict

        return _real_dict
