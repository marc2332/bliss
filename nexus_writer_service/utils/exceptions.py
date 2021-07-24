def iter_chained_exception(error, include_top=True):
    if include_top:
        yield error
    parent = error.__cause__  # explicitly chained
    while parent is not None:
        yield parent
        parent = parent.__cause__
    parent = error.__context__  # implicitly chained
    while parent is not None:
        yield parent
        parent = parent.__context__
