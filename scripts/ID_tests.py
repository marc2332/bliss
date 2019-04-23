#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import PyTango

ds_name = "//orion:10000/ID/ID/26"
ds = PyTango.DeviceProxy(ds_name)

undulators = list()
u_dict = dict()

print("")
print("ds = %s" % ds_name)
print("ds.state = %s" % ds.state())
print("ds.status = %s" % ds.status())

movable_names = ds.MovableNames
print("MovableNames = %r" % "  ".join(movable_names))

for undu in ds.MovableNames:
    u_name = undu.split("_")[0]
    u_letter = u_name[-1:]

    if u_name not in u_dict:
        u_dict[u_letter] = u_name

print("Undulators: ", u_dict)

print("UndulatorNames = %r" % "  ".join(ds.UndulatorNames))

print("UndulatorRevolverCarriage : %r " % ds.UndulatorRevolverCarriage)


print("#################################################################")


info_str = "DEVICE SERVER : %s \n" % ds_name
info_str += 'status="%s"\n' % str(ds.status()).strip()
info_str += "state=%s\n" % ds.state()
info_str += "mode=%s\n" % str(ds.mode)

info_str += "undu states= %s" % " ".join(map(str, ds.UndulatorStates))

print("info_str:")
print(info_str)


print("#################################################################")

# In [18]: ds.MovableNames
# Out[18]: ('U35a_GAP', 'U35a_TAPER', 'U35b_GAP', 'U35b_TAPER', 'U35c_GAP', 'U27c_GAP')


# In [16]: ds.UndulatorSrPositions
# Out[16]: array([ 26.1,  26.2,  26.3,  26.3])

# In [17]: ds.UndulatorRevolverCarriage
# Out[17]: array([False, False,  True,  True], dtype=bool)


# In [19]: ds.UndulatorRevolverCarriage
# Out[19]: array([False, False,  True,  True], dtype=bool)

# In [20]: ds.UndulatorNames
# Out[20]: ('U35a', 'U35b', 'U35c', 'U27c')


# ds.Abort                              ds.command_inout_asynch               ds.polling_status
# ds.Delivery                           ds.command_inout_raw                  ds.power
# ds.Enable                             ds.command_inout_reply                ds.powerdensity
# ds.EndFileWriting                     ds.command_inout_reply_raw            ds.powerdevicename
# ds.FileWritingLock                    ds.command_list_query                 ds.put_property
# ds.HasInjectionInterlock              ds.command_query                      ds.read_attribute
# ds.Init                               ds.connect                            ds.read_attribute_asynch
# ds.Injection                          ds.defaultCommandExtractAs            ds.read_attribute_reply
# ds.InjectionInterlock                 ds.delete_property                    ds.read_attributes
# ds.MaxPower                           ds.delivery                           ds.read_attributes_asynch
# ds.MaxPowerDensity                    ds.description                        ds.read_attributes_reply
# ds.Mode                               ds.dev_name                           ds.reconnect
# ds.MovableNames                       ds.enable                             ds.remove_logging_target
# ds.MovableStates                      ds.endfilewriting                     ds.removeundulator
# ds.Open                               ds.event_queue_size                   ds.reset
# ds.OperationState                     ds.filewritinglock                    ds.safe
# ds.Power                              ds.get_access_control                 ds.search
# ds.PowerDensity                       ds.get_access_right                   ds.set_access_control
# ds.PowerDeviceName                    ds.get_asynch_replies                 ds.set_attribute_config
# ds.RemoveUndulator                    ds.get_attribute_config               ds.set_green_mode
# ds.Reset                              ds.get_attribute_config_ex            ds.set_logging_level
# ds.Safe                               ds.get_attribute_list                 ds.set_source
# ds.Search                             ds.get_attribute_poll_period          ds.set_timeout_millis
# ds.Shutdown                           ds.get_command_poll_period            ds.set_transparency_reconnection
# ds.StartFileWriting                   ds.get_db_host                        ds.shutdown
# ds.State                              ds.get_db_port                        ds.startfilewriting
# ds.Status                             ds.get_db_port_num                    ds.state
# ds.TopUp                              ds.get_dev_host                       ds.status
# ds.U27c_GAP_Acceleration              ds.get_dev_port                       ds.stop_poll_attribute
# ds.U27c_GAP_FirstVelocity             ds.get_device_db                      ds.stop_poll_command
# ds.U27c_GAP_Position                  ds.get_events                         ds.subscribe_event
# ds.U27c_GAP_Velocity                  ds.get_fqdn                           ds.topup
# ds.U35a_GAP_Acceleration              ds.get_from_env_var                   ds.u27c_gap_acceleration
# ds.U35a_GAP_FirstVelocity             ds.get_green_mode                     ds.u27c_gap_firstvelocity
# ds.U35a_GAP_Position                  ds.get_idl_version                    ds.u27c_gap_position
# ds.U35a_GAP_Velocity                  ds.get_last_event_date                ds.u27c_gap_velocity
# ds.U35a_TAPER_Acceleration            ds.get_locker                         ds.u35a_gap_acceleration
# ds.U35a_TAPER_FirstVelocity           ds.get_logging_level                  ds.u35a_gap_firstvelocity
# ds.U35a_TAPER_Position                ds.get_logging_target                 ds.u35a_gap_position
# ds.U35a_TAPER_Velocity                ds.get_property                       ds.u35a_gap_velocity
# ds.U35b_GAP_Acceleration              ds.get_property_list                  ds.u35a_taper_acceleration
# ds.U35b_GAP_FirstVelocity             ds.get_source                         ds.u35a_taper_firstvelocity
# ds.U35b_GAP_Position                  ds.get_tango_lib_version              ds.u35a_taper_position
# ds.U35b_GAP_Velocity                  ds.get_timeout_millis                 ds.u35a_taper_velocity
# ds.U35b_TAPER_Acceleration            ds.get_transparency_reconnection      ds.u35b_gap_acceleration
# ds.U35b_TAPER_FirstVelocity           ds.hasinjectioninterlock              ds.u35b_gap_firstvelocity
# ds.U35b_TAPER_Position                ds.import_info                        ds.u35b_gap_position
# ds.U35b_TAPER_Velocity                ds.info                               ds.u35b_gap_velocity
# ds.U35c_GAP_Acceleration              ds.init                               ds.u35b_taper_acceleration
# ds.U35c_GAP_FirstVelocity             ds.injection                          ds.u35b_taper_firstvelocity
# ds.U35c_GAP_Position                  ds.injectioninterlock                 ds.u35b_taper_position
# ds.U35c_GAP_Velocity                  ds.is_attribute_polled                ds.u35b_taper_velocity
# ds.UndulatorDeviceNames               ds.is_command_polled                  ds.u35c_gap_acceleration
# ds.UndulatorModes                     ds.is_dbase_used                      ds.u35c_gap_firstvelocity
# ds.UndulatorNames                     ds.is_event_queue_empty               ds.u35c_gap_position
# ds.UndulatorRevolverCarriage          ds.is_locked                          ds.u35c_gap_velocity
# ds.UndulatorSrPositions               ds.is_locked_by_me                    ds.undulatordevicenames
# ds.UndulatorStates                    ds.lock                               ds.undulatormodes
# ds.abort                              ds.locking_status                     ds.undulatornames
# ds.add_logging_target                 ds.maxpower                           ds.undulatorrevolvercarriage
# ds.adm_name                           ds.maxpowerdensity                    ds.undulatorsrpositions
# ds.alias                              ds.mode                               ds.undulatorstates
# ds.attribute_history                  ds.movablenames                       ds.unlock
# ds.attribute_list_query               ds.movablestates                      ds.unsubscribe_event
# ds.attribute_list_query_ex            ds.name                               ds.write_attribute
# ds.attribute_query                    ds.open                               ds.write_attribute_asynch
# ds.black_box                          ds.operationstate                     ds.write_attribute_reply
# ds.cancel_all_polling_asynch_request  ds.pending_asynch_call                ds.write_attributes
# ds.cancel_asynch_request              ds.ping                               ds.write_attributes_asynch
# ds.command_history                    ds.poll_attribute                     ds.write_attributes_reply
# ds.command_inout                      ds.poll_command                       ds.write_read_attribute


print("")

print("")
print("")

bl_numbers = [
    "1",
    "2",
    "3",
    "6",
    "8",
    "9",
    "10",
    "11",
    "12",
    "13",
    "14",
    "15",
    "16na",
    "16ni",
    "17",
    "18",
    "19",
    "20",
    "21",
    "22",
    "23",
    "24",
    "26",
    "27",
    "28",
    "29",
    "30",
    "31",
    "32",
]

bl_numbers = [
    "1",
    "2",
    "3",
    "6",
    "9",
    "10",
    "11",
    "12",
    "13",
    "14",
    "15",
    "16na",
    "16ni",
    "17",
    "18",
    "19",
    "20",
    "21",
    "22",
    "23",
    "24",
    "26",
    "27",
    "28",
    "29",
    "30",
    "31",
    "32",
]

for bl_number in bl_numbers:
    ds_name = "//orion:10000/ID/ID/%s" % bl_number
    ds = PyTango.DeviceProxy(ds_name)
    print("ID", bl_number, ds.MovableNames)


# ID 1 ('U35a_GAP', 'U35a_TAPER', 'U27b_GAP', 'U35b_GAP', 'U27c_GAP', 'U27c_TAPER')
# ID 2 ('U35a_GAP', 'U35a_TAPER', 'U21-4b_GAP', 'U21-4b_TAPER', 'U21-4c_GAP', 'U21-4c_TAPER')
# ID 3 ('U35a_GAP', 'U35a_TAPER', 'U35b_GAP', 'U35b_TAPER', 'U32A_GAP', 'U32A_TAPER')
# ID 6 ('CPU18-1A_GAP', 'CPU18-1A_OFFSET', 'PPU27-12_GAP', 'PPU27-12_TAPER')
# ID 9 ('IVU20a_GAP', 'IVU20a_OFFSET', 'IVU17c_GAP', 'IVU17c_OFFSET')
# ID 10 ('U35a_GAP', 'U35a_TAPER', 'U27b_GAP', 'U35b_GAP', 'U27c_GAP', 'U27c_TAPER')
# ID 11 ('CPM18a_GAP', 'CPM18a_TAPER', 'CPM18a_OFFSET', 'IVU22b_GAP', 'IVU22b_OFFSET')
# ID 12 ('HU52b_GAPBX', 'HU52b_GAPBZ', 'HU52b_PHASE', 'HU38C_GAP', 'HU38C_OFFSET', 'HU38C_PHASE')
# ID 13 ('IVU18C_GAP', 'IVU18C_OFFSET', 'U35a_GAP', 'U35a_TAPER')
# ID 14 ('U35A_GAP', 'U35A_TAPER', 'U23B_GAP', 'U23B_TAPER', 'U24C_GAP', 'U24C_TAPER')
# ID 15 ('IVHU22A_GAP', 'IVHU22A_OFFSET', 'AW220C_GAP')
# ID 16na ('HPI26a_GAP', 'HPI26a_TAPER')
# ID 16ni ('U18-3C_GAP', 'U22-4C_GAP', 'U18-3D_GAP', 'U22-4D_GAP')
# ID 17 ('W125A_GAP', 'W150B_GAP', 'W150B_TAPER')
# ID 18 ('U27a_GAP', 'U20a_GAP', 'U27b_GAP', 'U20b_GAP', 'U20c_GAP', 'U27c_GAP')
# ID 19 ('PPU13A_GAP', 'PPU32A_GAP', 'W150B_GAP', 'W150B_TAPER', 'U32c_GAP', 'U17-6c_GAP')
# ID 20 ('U26a_GAP', 'U26a_TAPER', 'U32b_GAP', 'U26b_GAP', 'U32c_GAP', 'U26c_GAP', 'U32d_GAP', 'U26d_GAP')
# ID 21 ('U32a_GAP', 'U32a_TAPER', 'U42b_GAP', 'U42b_TAPER', 'U42c_GAP', 'U42c_TAPER')
# ID 22 ('U19A_GAP', 'U35A_GAP', 'U23C_GAP', 'U23C_OFFSET')
# ID 23 ('U20-2a_GAP', 'U20-2a_TAPER', 'U35c_GAP', 'U35c_TAPER')
# ID 24 ('U27a_GAP', 'U27a_TAPER', 'U27B_GAP', 'U27B_TAPER', 'U27c_GAP', 'U32C_GAP', 'U32d_GAP', 'U32d_TAPER')
# ID 26 ('U35a_GAP', 'U35a_TAPER', 'U35b_GAP', 'U35b_TAPER', 'U35c_GAP', 'U27c_GAP')
# ID 27 ('IVU23a_GAP', 'IVU23a_OFFSET', 'IVU23c_GAP', 'IVU23c_OFFSET')
# ID 28 ('U32a_GAP', 'U17-6a_GAP', 'U32b_GAP', 'U17-6b_GAP', 'U32c_GAP', 'U17-6c_GAP')
# ID 29 ('U35a_GAP', 'U35a_TAPER', 'IVU21c_GAP', 'IVU21c_OFFSET')
# ID 30 ('U21-2A_GAP', 'U21-2A_TAPER', 'PPU21-2B_GAP', 'PPU21-2B_TAPER', 'PPU35C_GAP', 'PPU35C_TAPER', 'PPU35D_GAP', 'PPU35D_TAPER')
# ID 31 ('U32a_GAP', 'U32a_TAPER', 'U32b_GAP', 'U32b_TAPER', 'U35c_GAP', 'U35c_TAPER')
# ID 32 ('HU88A_GAP', 'HU88A_OFFSET', 'HU88A_PHASE', 'HU88C_GAP', 'HU88C_OFFSET', 'HU88C_PHASE')

# ID30:
# PPU35C_GAP_Acceleration   mm/s2 (ex: 100) [;]
# PPU35C_GAP_FirstVelocity  mm/s  (ex: 0.1) [;]
# PPU35C_GAP_Position       mm    (ex: 15)  [10.8; 300]
# PPU35C_GAP_Velocity       mm/s  (ex: 5)   [0.027;5.1]
