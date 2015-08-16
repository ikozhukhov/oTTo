def get_hg_revision(path="."):
    """
    :rtype : str
    """
    try:
        from mercurial import ui, hg, error
    except ImportError:
        return "HG-unknown"
    try:
        repo = hg.repository(ui.ui(), path)
    except (error.RepoError, IndexError):
        return "HG-unknown"
    ctx = repo[None]
    tags = ctx.tags()
    rev = ctx.branch()

    if rev:
        if rev != "default":
            return u'HG-%s' % rev
    elif tags == "tip":
        return u'HG-tip'
    elif tags != "":
        return u'%s' % tags
