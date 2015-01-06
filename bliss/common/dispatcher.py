try:
  from louie import dispatcher
  from louie import robustapply
  from louie import saferef
except ImportError:
  from pydispatch import dispatcher
  from pydispatch import robustapply
  from pydispatch import saferef
  saferef.safe_ref = saferef.safeRef
  robustapply.robust_apply = robustapply.robustApply
