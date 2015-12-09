# -*- coding: utf-8 -*-

import sys
import os
from datetime import datetime


# General information about the project.
project = u'oTTo'
copyright = u'2010 - %s, CORAID Alumni' % datetime.now().year

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
sys.path.insert(1, "%s/src" % os.path.abspath(
    (os.path.abspath(os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))))))

extensions = ['sphinx.ext.autodoc', 'sphinx.ext.doctest', 'sphinx.ext.todo',
              'sphinx.ext.coverage', 'sphinx.ext.pngmath', 'sphinx.ext.viewcode']

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# The suffix of source file names.
source_suffix = '.rst'

# The encoding of source files.
# source_encoding = 'utf-8-sig'

# The master toctree document.
master_doc = 'index'

exclude_patterns = [u'settings.*']

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = 'sphinx'

# -- Options for HTML output ---------------------------------------------------
html_theme = 'default'
html_theme_path = ['_themes']
# html_static_path = ['_static']
htmlhelp_basename = 'ottodoc'
html_theme_options = {"bodyfont": 'Arial,Helvetica,sans-serif;'}
html_show_sphinx = False

# The name of an image file (relative to this directory) to place at the top
# of the sidebar.
html_logo = 'otto.png'

# The name of an image file (within the static path) to use as favicon of the
# docs.  This file should be a Windows icon file (.ico) being 16x16 or 32x32
# pixels large.
html_favicon = 'otto.ico'

# If true, links to the reST sources are added to the pages.
html_show_sourcelink = True

# Output file base name for HTML help builder.
htmlhelp_basename = 'ottodoc'

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title, author, documentclass [howto/manual]).
latex_documents = [
    ('index', 'otto.tex', u'otto Documentation',
     u'michaelian ennis, et al.', 'manual'),
]

# -- Options for manual page output --------------------------------------------

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [
    ('index', 'otto', u'otto Documentation',
     [u'michaelian ennis'], 1)
]
todo_include_todos = True
autodoc_member_order = 'alphabetical'
