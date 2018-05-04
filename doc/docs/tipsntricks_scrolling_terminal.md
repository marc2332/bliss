
# Terminal scrolling issue

## Once you start a bliss terminal you can not scroll up


Example session:

	linohlsson2:~ % . blissenv
	setting BLISS environment
	Using BLISS development
	(bliss_dev) linohlsson2:~ % bliss -s test
	.....
	
	
	.....
	TEST [8]: wa()
	Current Positions (user, dial)
	
		emi     theta    thetab    thetah        xb 
	-------  --------  --------  --------  -------- 
	8.50000  68.49165  -5.33800   5.54200  27.97800
	8.50000  68.49165  -5.33800   5.54200  27.97800
	
	TEST [9]:

On some terminal you try to scroll up and it immediately puts you back on the last line

### The fix for known terminals
	
#### xfce4-terminal
	Fix: Edit-> Preferences -> General: Untick `Scroll on output`
	     Click on `Close` and "Voila !"


