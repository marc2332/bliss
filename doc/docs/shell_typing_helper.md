# BLISS shell typing helper
To serve the demand of a simplified syntax when entering commands in the bliss shell (without additional parenthesis and commas compared to ‘spec’) a ‘typing helper’  has been put in place.  It is a tightrope walk to respect 
- only clean python code syntax
- enable scientist to type commands in similar way as they are used to e.g. in ‘spec’

## Tying in the shell
!!! note
    Here ⏎ represents pressing the Enter key and ␣ represents pressing the space bar

lets look at the ```wm``` command as example. Lets say we want to see the position of two motors m0 and m0.

In order for Bliss to be able to interpret the command we need

	$ wm(m0,m1)⏎

in ‘spec’ one would have typed
	
	$ wm␣m0␣m1⏎

the typing helper will map this way of tying the command to the proper python syntax without having to type ```(``` , ```,``` and ```)``` manually. It replaces ␣ by ```(``` or ```,``` where appropriate. Further it replaces ⏎ by ```)```⏎ in case this complets the input, or ```()```⏎ in case a the input reprensts a python callable. An example would be

	$ wa⏎
	
is transformed into

	$ wa()⏎

The insertion behaviour of ⏎ is also applied to ```;```.