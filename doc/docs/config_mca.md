
# MCA

## ROIs counters

To see which ROIs are defined:

    CYRIL [1]: simul_mca.rois
      Out [1]: Name         (center     left   right)   (start    stop)
               ----------  -------- -------- -------- -------- --------
               my_roi          600      400      200      200      800

### Raw manual method to add a ROI

Use `add_roi(<center>, <left>, <right>)` command to add a ROI.

 * center : index where to center the ROI
 * left : number of channels to include under the center position
 * right : number of channels to include over the center position

Example:

    CYRIL [3]: simul_mca.rois.add_roi("AuLa", 827, 20, 10)
    
    CYRIL [4]: simul_mca.rois
      Out [4]: Name        (center     left   right)   (start    stop)
               ---------- -------- -------- -------- -------- --------
               AuLa            827       20       10      807      837
               my_roi          600      400      200      200      800

This method to define ROIs is not very user friendly and will be
completed by higer level methods... TO BE CONTINUED...

