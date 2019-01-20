# Configuring the flex correlator

The correlator is split into two: server and the client.  You have to
first install the server on a Windows PC and then you will be able to
remotly connect with the client part.

## Server configuration

First install bliss with the dll (flex02-01.dll) to control the correlator.
Then you probably need a bat file to start the device server.

When you run the server, the default port is **8909**

### Bat file example

```
call C:\ProgramData\Miniconda3\Scripts\activate.bat C:\ProgramData\Miniconda3
call activate bliss
call bliss-flex-server flex
```

## Client configuration

You just need to specify the **address** of the rpc server

### YAML configuration file example

```YAML
 - name: flex
   module: correlator.flex
   class: Flex
   address: tcp://wid10flex1:8909
```