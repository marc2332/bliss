# Installation and configuration of XIA MCA

Installation of XIA devices is common to the 3 XIA MCA electronics:

* xmap
* mercury
* falconx

Devices are plugged in a windows (10 pro 64 bits) computer.

BLISS must be installed on the windows PC to be able to run a BLISS RPC server.

**Handel** is the library used to deal with XIA devices and data. Handel comes
with **ProSpect** software.

To access XIA device using the Handel library from BLISS runing on a linux
station, a BLISS rpc server named `bliss-handel-server` must be running on the
windows PC.


**ProSpect** is the windows software provided by XIA to control and calibrate
XIA devices.

There are 2 versions of ProSpect:

* ProSpect for Xmap and Mercury (merged with the deprecated *xManager*)
* ProSpect for FalconX


## Windows PC installation

!!! note
    Windows version must be 7 or 10 pro 64 bits


To make your life easier using a remote windows computer, you can install cygwin
and ssh on it:
http://wikiserv.esrf.fr/bliss/index.php/Full_Cygwin_%2B_OpenSSH_installation_on_a_Windows_host


### Installation of conda and BLISS

* download a conda installer:
    * [miniconda](https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe)
* launch installer:
    * "for all users"
    * "use as default python"
* Create a link from taskbar to anaconda shell
    * start / all program / anaconda3 / right click on anaconda shell / pin to taskbar
* create `bliss` Conda environment with python 3.7 and git
    * Start anaconda shell
    * `conda create -n bliss python=3.7 git pip`
* activate bliss environment: `conda activate bliss`
* add channels:
```
conda config --env --add channels esrf-bcu
conda config --env --append channels conda-forge
conda config --env --append channels tango-controls
```
* ensure some packages are installed:
    * `conda install git`
    * `conda install pip`
* clone and install BLISS
    * `git clone https://gitlab.esrf.fr/bliss/bliss bliss.git`
    * `cd bliss.git`
    * remove `pygraphviz` from `requirements-conda.txt`
    * `conda install --file requirements-conda.txt`
    * `python setup.py install`

* test bliss installation:
    ```
    C:\ python
    >>> import bliss
    >>>
    ```


### Installation of XIA software

* Install auto-extractable package `xia_bcu_deployment_0.1.exe` taken here:
  ftp://ftp.esrf.fr/dist/bliss/xia/xia_bcu_deployment_0.1.exe

* This bcu package provides Xia packages:
    * *ProSpect* for Falconx
        * version 1.1.24
    * *ProSpect* for Mercury and Xmap
        * version 1.1.12
    * *Handel* library for Mercury/Xmap devices
        * version 1.2.22 64 bits
    * *Handel* library for Falconx
        * version 1.1.20 64 bits

The packages are copied in `C:\blissadm\xia_software\` directory

!!! note
    Do not install ProSpect 1.1.26 because of drivers changes.

* Depending on the XIA device:
    * install the corresponding *ProSpect*
    * test connection to the device with *ProSpect*

!!! note "For the XMAP"
    PXI-PCI bus-coupler cards must be installed. see:
    http://wikiserv.esrf.fr/bliss/index.php/XIA_Electronics_Installation#XMAP_installation.2Fupgrade_on_windows_7_64_bits

!!! note "For the FalconX"
    * Connection to the falconX can be tested with a browser using address `http://192.168.200.201`
    * Check firware version (must be ??? 0.8.7 ???)


* Install Handel libraries and make them accessible:
    * Xmap/mercury: extract `handel-all-1.2.22-x64.zip` file (right clic on it, 7-zip / extract here...)
    * Falconx: idem with `handel-sitoro-fxn-1.1.20-x64.zip`
    * move it in the `blissadm` directory: `C:\blissadm\handel-all-1.2.22-x64`

* Create a batch script to start `bliss-handel-server`:
    * right clic "New / Text Document"
    * name it according to your device:
        * `FalconX-server.txt`
        * `Xmap-server.txt`
        * `Mercury-server.txt`
    * copy the following lines into the .txt file
    * change`.txt` into `.bat`

miniconda example script for Xmap/Mercury:
```
set root=c:\programdata\miniconda3
set path=%path%;C:\blissadm\handel-all-1.2.22-x64\lib
call %root%\scripts\activate.bat bliss
bliss-handel-server.exe
```

miniconda example script for FalconX:
```
set root=c:\programdata\miniconda3
set path=%path%;C:\blissadm\handel-sitoro-fxn-1.1.20-x64\lib
call %root%\scripts\activate.bat bliss
bliss-handel-server.exe
```

### Developper's details

`bliss-handel-server` start-up script is created at installation using
the **entry_points** definitions in `setup.py` of BLISS repository.

```python
entry_points={
     "console_scripts": [
          ...
          "bliss-handel-server = bliss.controllers.mca.handel.server:main",
          ] }
```

The wrapping of the Handel library is made with cffi. see:
`bliss/controllers/mca/handel/_cffi.py`



## Configuration in BLISS


Example for mercury:
```yaml
- name: mercury
  module: mca
  class: Mercury
  url: tcp://wfamexia:8000
  configuration_directory: C:\\blissadm\\mercury\\config\\BM16
  default_configuration: Vortex3_Mercury4ch_05us_Hg.ini
```

Example for FalconX:
```yaml
- name: fxid21
  module: mca
  class: FalconX
  url: tcp://wid214:8000
  configuration_directory: C:\\blissadm\\falconx\\config\\ID21
  default_configuration: falconxn.ini
```

Example for Xmap:
```yaml
- name: fxid16
  module: mca
  class: XMAP
  url: tcp://wid421:8000
  configuration_directory: C:\\blissadm\\falconx\\config\\ID42
  default_configuration: xmap.ini

```

## NOTES:

Python script to parse binary mapping data: http://support.xia.com/default.asp?W882


