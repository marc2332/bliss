# 2D detectors-CCD (with Lima) #



2D detectors (CCD) supported by Lima can be controlled in BLISS via the BLISS `Lima` class.

This class uses the usual Lima Tango device server to access the detector.


## Configuration ##

    beamline_configuration/
    ├── eh2
    │   ├── cameras
    │   │   ├── andor1.yml
    │   │   ├── andor2.yml
    │   │   ├── cdte22.yml
    │   │   ├── eiger1.yml
    │   │   └── mpx22.yml

Example of YAML configuration file:

    % cat mpx22.yml
       name: mpx22
       class: Lima
       tango_url: id42/limaccd/mpx_22
       tango_timeout: 120

Example of usage in a BLISS session:


    - name: eh2_exp
      class: Session
      setup-file: ./eh2_exp.py
      config-objects:
        - p201_20
        - bpmdiode
        - mpx22
    #
    # a specific chain for setting 2D detectors in external trigger mode only
    #
    - default_chain_eh2
    
    - name: default_chain_eh2
      plugin: default
      chain_config:
        - device: $mpx22
          acquisition_settings:
            acq_trigger_mode: EXTERNAL_TRIGGER_MULTI
          master: $p201_20


Example to add a pseudo axis to drive the Maxipix's threshold:

    if hasattr(setup_globals,'mpx22'):
        mpxthl = SoftAxis('mpxthl', mpx22.camera,
                           position='energy_threshold',
                           move='energy_threshold')


