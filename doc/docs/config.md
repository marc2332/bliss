
# Beacon and YAML

## Beacon

### plugin

Some Beacon plugins are provided to instantiate YAML configuration
tree into BLISS python objects usable in a session or a BLISS
sequence.

* `session`: to furnish configuration 
* `emotion`: to instantiate BlissAxis objects (motors)
* `ct2`: for P201 counting cards
* `keithley`: for Keithley electrometers
* `temperature`: for temperature controllers
* `comm`: for standalone communication objects (serial lines, TCP, GPIB)
* `bliss`: a generic plugin to instantiate controllers

A new plugin can be easily created by a developer to fit new needs.

## YAML in brief

* .yml is the extention used for YAML formated files.
* YAML stands for Yet Another Markup Language
* `$` character indicates a **reference** to an existing axis


see also :

* http://yaml.org/
* https://fr.wikipedia.org/wiki/YAML
* in french:
    * http://sweetohm.net/article/introduction-yaml.html
    * https://learnxinyminutes.com/docs/fr-fr/yaml-fr/
* on-line parser: http://yaml-online-parser.appspot.com/

