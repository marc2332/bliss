# Installation and configuration of XIA MCA

Installation of XIA devices is common to the 3 XIA MCA electronics:

* xmap
* mercury
* falconx

Devices are plugged in a windows (10 pro 64 bits) computer.

BLISS must be installed on the windows PC to be able to run a BLISS RPC server.

**Handel** is the library used to deal with XIA devices and data. Handel comes
with **ProSpect** which is the windows software provided by XIA to test and
calibrate XIA devices.

To access XIA device using the Handel library from BLISS running on a linux
station, a BLISS rpc server named `bliss-handel-server` must be running on the
windows PC.


There are 2 versions of ProSpect:

* ProSpect for Xmap and Mercury (merged with the deprecated *xManager*)
* ProSpect for FalconX


## Windows PC installation

!!! note "Windows version must be 7 or 10 pro 64 bits"
    Windows 7 is now deprecated.

### Installation of conda

* download a conda installer:
    * [miniconda](https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe)
* launch installer:
    * tick "for all users"
    * tick "use as default python"
    * "Destination Folder:" `C:\ProgramData\Miniconda3`
    * ??? untick ??? "Add Miniconda3 to the system PATH environment variable"
    * ??? tick ??? "Register Miniconda3 as the system Python 3.8"
* Create a link from taskbar to anaconda shell
    * win7: start / all program / anaconda3 / right click on anaconda shell / pin to taskbar
    * win10: Windows / type anaconda / highlight "Anaconda Powershell Prompt" + select "Pin to taskbar" on the right panel
* create `bliss` Conda environment with python 3.7 and git
    * Start anaconda shell
    * `conda create -n bliss python=3.7 git pip`
* activate bliss environment: `conda activate bliss`
* install git support for python: `conda install gitpython`
* Configue channels:

```
conda config --env --set channel_priority false
conda config --env --add channels conda-forge
conda config --env --append channels defaults
conda config --env --append channels esrf-bcu
conda config --env --append channels tango-controls
```

### Installation of BLISS

* install BLISS conda package for windows
    ```
    conda install bliss
    ```

*Alternatively*, in order to install BLISS from the sources or to devellop or to
have on-the-edge version:

* ensure some packages are installed:
    ```
    conda install git
    conda install pip
    ```
* clone and install BLISS
    ```
    git clone https://gitlab.esrf.fr/bliss/bliss bliss.git
    
    cd bliss.git
    
    conda install --file requirements-conda-win64.txt
    
    pip install -e . --no-deps
    ```

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
        * version 1.1.21 64 bits

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
    * Check firware version (must be 20.1.0)

* Install Handel libraries and make them accessible:
    * Xmap/mercury: extract `handel-all-1.2.22-x64.zip` file (right clic on it, 7-zip / extract here...)
    * Falconx: idem with `handel-sitoro-fxn-1.1.21-x64.zip`
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
set path=%path%;C:\blissadm\handel-sitoro-fxn-1.1.21-x64\lib
call %root%\scripts\activate.bat bliss
bliss-handel-server.exe
```

### Developer's details

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
- name: fxid42
  module: mca
  class: FalconX
  url: tcp://wid421:8000
  configuration_directory: C:\\blissadm\\falconx\\config\\ID42
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

## NOTES

Python script to parse binary mapping data
http://support.xia.com/default.asp?W882


