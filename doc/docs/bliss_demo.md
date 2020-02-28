## Starting BLISS demo processes

BLISS demonstration processes can be started with a script available in BLISS source code repository,
within an environment corresponding to the testing environment (see [Test setup](dev_testing.md#Test setup))

```bash
cd <bliss_source_directory>
cd demo
./start_demo_servers
```

The script tells the command line to use to start the BLISS demo session:

```
##################################################################################
# start BLISS in another Terminal using                                          #
# > TANGO_HOST=dagobah:10000 BEACON_HOST=dagobah:10001 bliss -s demo_session     #
#                                                                                #
# press ctrl+c to quit this process                                              #
##################################################################################
```

