##########################
Bliss Version 1.0 Features
##########################

Features to be implemented in the version 1.0 of the BLISS project:

Configuration
=============

* File based static configuration in YAML format
* Memory based dynamic settings. Usage of REDIS for setting storage
* Documented API for configuration reading and setting writing must be available
* Description and templates for hardware controller configuration
* Coherent and documented configuration for all hardware controllers available in the project

Hardware Integration
====================

For a first implementation on the beamlines a set of hardware controllers must be available in the system to set-up the most standard scans. All hardware controllers must have the possibility to access the hardware installed on remote computers.

* Motors: The BlissAxis module has to include controllers for IcePap, PI piezo motors, ??????
	* Calculational axis controllers must be available
* MUSST and OPIOM controllers for synchronization and multiplexing
	* Definition of the possible trigger modes for hardware and software triggering
* Detectors: LIMA controller to include all 2D detectors
* Counters: P201 controller, LIMA ROI counters, MUSST channels
	* Calculational counter controllers must be available
* Temperature: A temperature module with controllers for Oxford, Eurotherm, ?????

Scanning and Data Acquisition
=============================

* Step scans and continuous scans must be available in a coherent way
* Hardware and software triggered continuous scans must be possible with triggering in time and position
* It must be possible to define measurement groups to allow hardware grouping for different acquisitions
* Acquisition results will be stored in HDF5 format. All acquired data will be referenced from the main data file.
* Data of the actual and last acquisitions will be available in the REDIS database for online data viewing or online data analysis
* A documented API for online data reading must be available

User Interfaces
===============

* A command line interface running python sequences
	* A set of standard python sequences for the most common tasks
	* Clear session definition with a persistent set-up
* Online plotting GUI to monitor scan progress and main parameters
* Online data display GUI based on the online data reading API


