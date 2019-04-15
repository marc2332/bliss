# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Classes related to the alias handling in Bliss

The alias serves the following purposes:
- Handle potential duplication of motor names in a beamline-wide configuration 
- Shorten key names e.g. in the hdf5 files while conserving uniqueness of the keys 
"""
import weakref
from tabulate import tabulate

from bliss.config import static
from bliss import setup_globals
from bliss.common import session


class AliasMixin(object):
    """Class that can be inherited to have alias related properties"""

    def set_alias(
        self, alias, export_to_globals=True, remove_original=False, hide_controller=True
    ):
        if self.has_alias:
            raise RuntimeError(
                f"Alias This object (Alias: '{self.alias}', Name '{self.name}' has already an alias!"
            )

        """Assign an alias for this object"""
        alias_config = {
            "original_name": self.name,
            "alias_name": alias,
            "export_to_globals": export_to_globals,
            "remove_original": remove_original,
            "hide_controller": hide_controller,
        }

        if not hasattr(setup_globals, "ALIASES"):
            setattr(
                setup_globals, "ALIASES", Aliases(self, session.get_current().env_dict)
            )

        setup_globals.ALIASES.create_alias(
            **alias_config,
            disable_link_search=True,
            disable_setup_globals_lookup=True,
            object_ref=self,
        )

    def remove_alias(self):
        """Remove alias for this object"""
        raise NotImplementedError

    @property
    def alias(self):
        """Returns the alias name (str) or None
        if no alias has been assigned to this object"""
        a = self.alias_object
        if a is not None:
            return a.name
        else:
            return None

    @property
    def alias_object(self):
        """Returns the Alias Object that handles the alias for this class.
        Returns None if no alias has been assigned"""
        if hasattr(setup_globals, "ALIASES"):
            a = setup_globals.ALIASES.aliases.get(self.name.replace(":", "."), None)
            if a is None and hasattr(self, "fullname"):
                return setup_globals.ALIASES.aliases.get(
                    self.fullname.replace(":", "."), None
                )
            else:
                return a
        else:
            return None

    @property
    def has_alias(self):
        """Check an alias has been assigned to this object"""
        return self.alias_object != None

    @property
    def alias_or_name(self):
        """Returns alias if assigned, otherwise it returns the name of the object"""
        if self.has_alias:
            return self.alias_object.name
        else:
            return self.name

    @property
    def alias_or_fullname(self):
        """Returns alias if assigned, otherwise it returns the fullname of the object
        as fallback it returns the name of the object if .fullname property does not exist.
        In case the hide_controller flag has been unset during creation of the alias the 
        controller name will be added in front of the alias (only relevant for channels)"""
        if self.has_alias:
            if self.alias_object._hide_controller:
                return self.alias
            else:
                if hasattr(self, "acq_device"):
                    return self.acq_device.name + ":" + self.alias
                else:
                    return self.alias
        elif hasattr(self, "fullname"):
            return self.fullname
        else:
            return self.name


class Alias(object):
    """One Alias object is created for each alias that assigned. In order work correctly 
    the Alias must be created through the Aliases class."""

    _object_ref = None

    def __init__(
        self,
        alias_name,
        original_name,
        hide_controller=True,
        disable_link_search=False,
        disable_setup_globals_lookup=False,
    ):
        """Constructor or Alias. 
        If there is a python object in setup_globlas or the env_dict of the repl that has a
        'name' or 'fullname' property corresponding to the 'original_name' it will be linked 
        to this alias if not specified differently.
        
        Parameters:
        alias_name: Name that will be assigned to this alias (String)
        original_name: Name of the object that should be aliased (String)
        
        Keyword Arguments:
        hide_controller: Should the controller name be hidden when called via '.alias_or_fullname'. 
                         Mainly interesting for channels and axes (Boolean, default:True)
        disable_link_search: Don't search for corresponding python object in counter list of the session (Boolean, default:False)
        disable_setup_globals_lookup: Don't search for corresponding python object in setup_globals (Boolean, default:False)
        """
        self._name = alias_name
        self._original_name = original_name
        self._hide_controller = hide_controller

        # check if the name of the alias is allowed to take etc.
        if alias_name == None:
            raise RuntimeError(
                f"Alias for '{original_name}' can not be set! no alias supplied."
            )

        elif hasattr(setup_globals, alias_name):
            raise RuntimeError(
                f"Alias '{alias_name}' for '{original_name}' can not be set! An object with its name already exists in setup_globals"
            )
        elif alias_name in setup_globals.ALIASES.aliases:
            raise RuntimeError(
                f"Alias '{alias_name}' for '{original_name}' can not be set! There is alreadey an Object or Alias with this name"
            )
        elif alias_name in static.get_config().names_list:
            raise RuntimeError(
                f"Alias '{alias_name}' for '{original_name}' can not be set! {alias_name} already used as name-key in config"
            )

        if not disable_setup_globals_lookup:
            # check if oject exists in setup globals
            if hasattr(setup_globals, original_name):
                self._link_to(getattr(setup_globals, original_name))

        # check if there is a counter around that can be linked to this alias
        if not disable_link_search:
            from bliss.common.utils import counter_dict

            for key, item in counter_dict().items():
                if key == original_name:
                    self._link_to(item)
                    break
                elif item.name == original_name:
                    self._link_to(item)
                    break

        print(f"Alias '{alias_name}' added for '{original_name}'")

    def _turn_into_weakref(self):
        """Turn reference to python object corresponding to this alias into weak reference. 
        In case the original object is deleted, the alias will also be removed from setup_globals.ALIASES"""
        if (
            not isinstance(self._object_ref, weakref.ReferenceType)
            and self._object_ref is not None
        ):
            self._object_ref = weakref.ref(
                self._object_ref, self._remove_alias_on_orig_del
            )

    def _turn_into_hardref(self):
        """Turn reference to python object corresponding to this alias into direct (hard) reference. 
        The original object will not be destroyed as long as it is kept in setup_globals.ALIASES"""
        if (
            isinstance(self._object_ref, weakref.ReferenceType)
            and self._object_ref is not None
        ):
            self._object_ref = self._object_ref()

    def _remove_alias_on_orig_del(self, reference):
        """callback function for weakref"""
        print(f"DELETE {self.name}")
        setup_globals.ALIASES._remove_alias(self)

    def _link_to(self, obj):
        """link a python object to this alias via its reference"""
        self._object_ref = obj

    @property
    def original_name(self):
        """ (old) name that is aliased through this alias. This is NOT the (new) name assigned to through alias"""
        return self._original_name

    @property
    def object_ref(self):
        """Returns the python object referenced in this alias."""
        if isinstance(self._object_ref, weakref.ReferenceType):
            return self._object_ref()
        else:
            return self._object_ref

    @property
    def has_object_ref(self):
        """Returns 'True' if there is a python object linked to this alias"""
        return self._object_ref is not None

    @property
    def name(self):
        """Returns the name of this alias"""
        return self._name

    def export_alias(self):
        """Exports the alias to the repl env_dict and setup_globals. Only works if 
        there is a python object assigned to this alias, otherwise it raises a RuntimeError """
        raise NotImplementedError

    def __repr__(self):
        return f"Alias Object: {self._name} --> {self._original_name}"


class Aliases(object):
    """Class that is created once on session level, exported to setup_globals.ALIASES and manages 
    a dict of all aliases existing in the session"""

    _aliases = None  # dict original_object_name:Alias_object

    def __init__(self, session, env_dict):
        """-populate aliases dict and export it to env_dict"""
        self._aliases = dict()
        self._env_dict = env_dict

    def get(self, alias):
        """Returns the original python object link an alias. 
        Parameters:
        - alias: Name (str) of the alias for which the original python object should be returned.
        
        Raises 'RuntimeError' if no Alias with the provided alias name exists 
        and 'ValueError' if there is no python object linked the specified alias"""
        a = None
        for key, item in self._aliases.items():
            if item.name == alias:
                a = item

        if a == None:
            raise RuntimeError(f'No Alias called "{alias}" found!')
        if a.has_object_ref:
            return a.object_ref
        else:
            raise ValueError(f'No Python object linked to alias "{alias}" !')

    def add_alias(self, alias_obj):
        """Add an alias object to the setup_globals.ALIASES"""
        raise NotImplementedError

    def replace_alias(self, new_alias_obj):
        """Removes an existing alias from setup_globals.ALIASES identified by its name and adds a new one"""
        raise NotImplementedError

    def create_alias(
        self,
        alias_name,
        original_name,
        disable_link_search=False,
        disable_setup_globals_lookup=False,
        export_to_globals=True,
        remove_original=False,
        hide_controller=True,
        object_ref=None,
    ):
        """Create an alias and add it to setup_globals.ALIASES
        Parameters:
        - alias_name: (new) name that will be assigned to the alias
        - original_name: (old) name that will be masked by the alias_name
        
        Keyword Arguments:
        - export_to_globals: Alias will be exported to env_dict of repl and setup_globals (Boolean, default:True) 
        - remove_original: Orignal name will be removed from env_dict of repl and setup_globals (Boolean, default:False)
        - hide_controller: Should the controller name be hidden when called via '.alias_or_fullname'. 
                           Mainly interesting for channels and axes (Boolean, default:True)
        - disable_link_search: Don't search for corresponding python object in counter list of the session (Boolean, default:False)
        - disable_setup_globals_lookup: Don't search for corresponding python object in setup_globals (Boolean, default:False)
        - object_ref: python object that should be linked to this alias
        """

        alias = Alias(
            alias_name,
            original_name,
            hide_controller,
            disable_link_search,
            disable_setup_globals_lookup,
        )
        self._aliases.update({original_name: alias})

        if object_ref is not None:
            alias._link_to(object_ref)

        if alias.has_object_ref and export_to_globals:
            setattr(setup_globals, alias.name, alias.object_ref)
            self._env_dict.update({alias.name: alias.object_ref})
            if remove_original:
                alias._turn_into_hardref()
                if hasattr(setup_globals, original_name):
                    delattr(setup_globals, original_name)
                if original_name in self._env_dict:
                    self._env_dict.pop(original_name)

    def _remove_alias(self, alias):
        """removes alias from setup_globals.ALIASES"""
        print(f"Alias {alias.name} will be removed from global list")
        if alias.original_name in self._aliases:
            del self._aliases[alias.original_name]
            print(f"Alias {alias.name} removed from global list")
        else:
            raise RuntimeError(f"Alias for '{alias.original_name}' not in global list")

    def _list_aliases(self):
        table_info = []
        for original_name, alias in self._aliases.items():
            table_info.append([alias.name, original_name, alias.has_object_ref])
        return str(
            tabulate(table_info, headers=["Alias", "Original name", "Linked to py obj"])
        )

    def list_aliases(self):
        """Display the list of  list all aliases"""
        print("")
        print(self._list_aliases())
        print("")

    @property
    def aliases(self):
        """returns a dict of alias objects"""
        return self._aliases

    def __repr__(self):
        return self._list_aliases()

    def close(self):
        for obj_name, obj in self._aliases.items():
            if hasattr(setup_globals, obj.name):
                delattr(setup_globals, obj.name)
            if not hasattr(setup_globals, obj_name) and obj.has_object_ref:
                try:
                    obj.object_ref.__close__()
                except Exception:
                    pass
