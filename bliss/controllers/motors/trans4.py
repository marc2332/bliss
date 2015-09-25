

"""
Bliss controller fo 4-motors Q-Sys support table for transfocators.
(ID22 - ID28? ...)


dh dr ur uh : aliases for real motors
              dh = downstream hall
              dr = downstream ring
              ur = upstream ring
              uh = upstream hall
ty tz thetay thetaz : aliases for calculated/virtual motors
              ty = alias for calculated y translation
              tz = alias for calculated z translation
              thetay = alias for calculated y rotation
              thetaz = alias for calculated z rotation

d1 : half distance in x direction (in mm) between the two moving blocks.
d3 : distance in z direction (in mm) between pivot plane and the top plate.

POI : point of interest (rotation center)

NOTE : We are using orientation conventions used on Q-Sys document.


<---X---Z
        |
        |
        Y
        |
        |
        V

   M2=DR                M3=UR
            POI
               X           <------------------------- BEAM

   M1=DH       |        M4=UH
    |          |
    |<---D1--->|


Example configuration (from ID22):
==================================
<config>
  <controller class="IcePAP">
    <host value="iceid221" />
    <libdebug value="1" />
    <axis name="tfdh">
      <address value="21" />
      <steps_per_unit value="100" />
      <backlash value="0.1" />
      <velocity value="6000" />
    </axis>
    <axis name="tfdr">
      <address value="22" />
      <steps_per_unit value="100" />
      <backlash value="0.1" />
      <velocity value="6000" />
    </axis>
    <axis name="tfur">
      <address value="23" />
      <steps_per_unit value="100" />
      <backlash value="0.1" />
      <velocity value="6000" />
    </axis>
    <axis name="tfuh">
      <address value="24" />
      <steps_per_unit value="100" />
      <backlash value="0.1" />
      <velocity value="8000" />
    </axis>
  </controller>
  <controller class="trans4">
    <axis name="tfdh" tags="real dh" />
    <axis name="tfdr" tags="real dr" />
    <axis name="tfur" tags="real ur" />
    <axis name="tfuh" tags="real uh" />
    <axis name="tfroty" tags="thetay" />
    <axis name="tfrotz" tags="thetaz" />
    <axis name="tfty"  tags="ty" />
    <axis name="tftz"  tags="tz" />
    <d1 value="180" />
    <d3 value="30" />
  </controller>
</config>
"""

from bliss.controllers.motor import CalcController
import math


class trans4(CalcController):
    def __init__(self, *args, **kwargs):
        CalcController.__init__(self, *args, **kwargs)

        self.d1 = self.config.get("d1", float)
        self.d3 = self.config.get("d3", float)

    def calc_from_real(self, positions_dict):
        '''
        Returns calculated/virtual motor positions (as a dictionary) given real ones.
        Units:
            Distances d1 and d3, real motors positions and calculated/virtual z and y
            motor positions are in millimeters.
            Calculated/virtual rotation around y and z axis are first calculated
            in radians and then transformed into degrees for the dictionnary
            returned by this function.
        '''
        d1 = self.d1
        # d3 = self.d3
        dh = positions_dict["dh"]
        dr = positions_dict["dr"]
        ur = positions_dict["ur"]
        uh = positions_dict["uh"]

        # Modif 04.Nov.2014
        ty = ((ur - uh) - (dh - dr)) / 4
        # tz = ((dh + dr + ur + uh) / 4) + d3
        tz = (dh + dr + ur + uh) / 4
        thetay = ((ur + uh) - (dh + dr)) / (4 * d1)
        thetaz = ((dh - dr) + (ur - uh)) / (4 * d1)

        # Angles (thetay and thetaz) are in radians.
        # Must transform angles into degrees before the values are returned
        # to the user.
        thetay = thetay * (180.0 / math.pi)
        thetaz = thetaz * (180.0 / math.pi)

        _virt_dict = {"thetay": thetay,
                      "thetaz": thetaz,
                      "ty": ty,
                      "tz": tz}

        # print _virt_dict
        return _virt_dict

    def calc_to_real(self, axis_tag, positions_dict):
        '''
        Returns real motors positions (as a dictionary) given virtual ones.
        Units:
        Distances d1 and d3, real motors positions and calculated/virtual z and y
        motor positions are in millimeters.
        Rotation around Y-axis(thetay) and Z-axis(thetaz) are in degrees and must
        be first transformed into radians before being used in formulas which calculate
        real motor positions from the calculated/virtual motor positions.
        '''

        d1 = self.d1
        # d3 = self.d3
        ty = positions_dict["ty"]
        tz = positions_dict["tz"]
        thetay = positions_dict["thetay"]
        thetaz = positions_dict["thetaz"]

        # Angles (thetay and thetaz) are in degrees.
        # Must transform them into radians since
        # radians are expected in formulas below
        thetay = thetay * (math.pi / 180.0)
        thetaz = thetaz * (math.pi / 180.0)

        dh = tz - ty + d1 * thetaz - d1 * thetay
        dr = tz + ty - d1 * thetaz - d1 * thetay
        ur = tz + ty + d1 * thetaz + d1 * thetay
        uh = tz - ty - d1 * thetaz + d1 * thetay

        _real_dict = {"dh": dh,
                      "dr": dr,
                      "ur": ur,
                      "uh": uh}

        # print _real_dict
        return _real_dict

