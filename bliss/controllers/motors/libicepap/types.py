"""IcePAP library"""


#-------------------------------------------------------------------------
# Standard modules
#
import numpy


#-------------------------------------------------------------------------
# Library modules
#
import globals
import axis  as libaxis




#-------------------------------------------------------------------------
# Class definition
#
class AxisList(list):
    """List of axis objects

    l=AxisList(axis1, axis2)
    l=AxisList()
 
    l.append(axis3)
    print l.axis_names()

    """

    def __init__(self, *args):
        """Standard list construcor"""

        # Will raise an exception if axis is a wrong object
        for axis in args:
            axis_to_name(axis)

        # Let the underlying list class do the job
        super(AxisList, self).__init__(args)

    def append(self, axis):
        """Append an axis"""

        # Will raise an exception if axis is a wrong object
        axis_to_name(axis)

        # Let the underlying list class do the job
        list.append(self, axis)

    def axis_names(self):
        """Returns a list of the axis names currently in the dictionary"""
        return [axis.name() for axis in list(self)]

#-------------------------------------------------------------------------
# Class definition
#
class PosList(dict):
    """List of axis/position pairs

    l=PosList([axis1, 100.1])
    l=PosList()

    l[axis1] = 100.1
    l[axis2] = 200.2
  
    l.clear()
    print l.axis_names()

    print l.axis_str(axis1)
    print l.all_axis_str()

    """

    def __init__(self, *args):
        """Standard dictionary construcor"""

        # Will raise an exception if axis is a wrong object
        for axis, position in args:
            libaxis.axis_to_name(axis)
        
        # Let the underlying dictionnary class do the job
        super(PosList, self).__init__(args)

    def __setitem__(self, axis, pos):
        """Append a pair of axis/position"""

        # Will raise an exception if axis is a wrong object
        libaxis.axis_to_name(axis)

        # Let the underlying dictionnary class do the job
        dict.__setitem__(self, axis, numpy.double(pos))

    def axis_names(self):
        """Returns a list of the axis names currently in the dictionary"""
        return [axis.name() for axis in dict.keys(self)]

    def axis_str(self, axis):
        """Returns a string with axis name and position"""

        # Convert postions from float to int just for display
        return "%s:%ld"%(axis.name(), self[axis])

    def all_axis_str(self):
        """Returns a string with all axis names and position"""
        return ' '.join([self.axis_str(a) for a in dict.keys(self)])



#-------------------------------------------------------------------------
# Class definition
#
class VelList(dict):
    """List of axis/velocity pairs

    l=VelList([axis1, 2000])
    l=VelList()

    l[axis1] = 2000
  
    l.clear()
    print l.axis_names()

    print l.axis_str(axis1)
    print l.all_axis_str()

    """

    def __init__(self, *args):
        """Standard dictionary construcor"""

        # Will raise an exception if axis is a wrong object
        for axis, velocity in args:
            libaxis.axis_to_name(axis)
        
        # Let the underlying dictionnary class do the job
        super(VelList, self).__init__(args)

    def __setitem__(self, axis, vel):
        """Append a pair of axis/velocity"""

        # Will raise an exception if axis is a wrong object
        libaxis.axis_to_name(axis)

        # Let the underlying dictionnary class do the job
        # Warning: the velocity returned by IcePAP can be in scientific 
        # notation which is not readable with pure int()
        dict.__setitem__(self, axis, int(float(vel)))

    def axis_names(self):
        """Returns a list of the axis names currently in the dictionary"""
        return [axis.name() for axis in dict.keys(self)]

    def axis_str(self, axis):
        """Returns a string with axis name and velocity"""
        return "%s:%ld"%(axis.name(), self[axis])

    def all_axis_str(self):
        """Returns a string with all axis names and velocities"""
        return ' '.join([self.axis_str(a) for a in dict.keys(self)])




#-------------------------------------------------------------------------
# Class definition
#
class AcctimeList(dict):
    """List of axis/acceleration time pairs

    l=AcctimeList([axis1, 0.125])
    l=AcctimeList()

    l[axis1] = 0.125
  
    l.clear()
    print l.axis_names()

    print l.axis_str(axis1)
    print l.all_axis_str()

    """

    def __init__(self, *args):
        """Standard dictionary construcor"""

        # Will raise an exception if axis is a wrong object
        for axis, acctime in args:
            libaxis.axis_to_name(axis)
        
        # Let the underlying dictionnary class do the job
        super(AcctimeList, self).__init__(args)

    def __setitem__(self, axis, acctime):
        """Append a pair of axis/acceleration time"""

        # Will raise an exception if axis is a wrong object
        libaxis.axis_to_name(axis)

        # Let the underlying dictionnary class do the job
        dict.__setitem__(self, axis, numpy.double(acctime))

    def axis_names(self):
        """Returns a list of the axis names currently in the dictionary"""
        return [axis.name() for axis in dict.keys(self)]

    def axis_str(self, axis):
        """Returns a string with axis name and acceleration time"""
        return "%s:%f"%(axis.name(), self[axis])

    def all_axis_str(self):
        """Returns a string with all axis names and acceleration times"""
        return ' '.join([self.axis_str(a) for a in dict.keys(self)])



#-------------------------------------------------------------------------
# Class definition
#
class StatusList(dict):
    """List of axis/status pairs

    l=StatusList([axis1, 0xaabbccdd])
    l=StatusList()

    l[axis1] = 0xaabbccdd
    l[axis2] = 0xdefecada
  
    print l.axis_hex(axis2)
    print l.all_axis_hex()

    """

    def __init__(self, *args):
        """Standard dictionary construcor"""

        # Will raise an exception if axis is a wrong object
        for axis, status in args:
            libaxis.axis_to_name(axis)
        
        # Let the underlying dictionnary class do the job
        super(StatusList, self).__init__(args)

    def __setitem__(self, axis, sta):
        """Append a pair of axis/status"""

        # Will raise an exception if axis is a wrong object
        libaxis.axis_to_name(axis)

        # Let the underlying dictionnary class do the job
        dict.__setitem__(self, axis, numpy.uint32(sta))

    def axis_names(self):
        """Returns a list of the axis names currently in the dictionary"""
        return [axis.name() for axis in dict.keys(self)]

    def axis_hex(self, axis):
        """Returns a string with axis name and hexadecimal status"""
        return "%s:0x%08x"%(axis.name(), self[axis])

    def all_axis_hex(self):
        """Returns a string with all axis names and hexadecimal status"""
        return ' '.join([self.axis_hex(a) for a in dict.keys(self)])




#-------------------------------------------------------------------------
# Class definition
#
class AnswerList(dict):
    """List of axis/string pairs 

    l=AnswerList()

    l[axis1] = "blabla"
    l = g.command("?ID")
    
    print l.axis_str(axis2)
    print l.all_axis_str()

    """

    def __init__(self, *args):
        """Standard dictionary construcor"""

        # Will raise an exception if axis is a wrong object
        for axis, str in args:
            libaxis.axis_to_name(axis)

        # Let the underlying dictionnary class do the job
        super(AnswerList, self).__init__(args)

    def __setitem__(self, axis, str):
        """Append a pair of axis/string"""

        # Will raise an exception if axis is a wrong object
        libaxis.axis_to_name(axis)

        # Let the underlying dictionnary class do the job
        dict.__setitem__(self, axis, str)

    def axis_names(self):
        """Returns a list of the axis names currently in the dictionary"""
        return [axis.name() for axis in dict.keys(self)]

    def axis_str(self, axis):
        """Returns a string with axis name and string"""
        return "%s:%s"%(axis.name(), self[axis])

    def all_axis_str(self):
        """Returns a string with all axis names and strings"""
        return ' '.join([self.axis_str(a) for a in dict.keys(self)])

