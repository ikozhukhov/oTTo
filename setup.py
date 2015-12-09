#!/bin/env python2.7
from commands import getstatusoutput

from setuptools import setup, find_packages

(status, output) = getstatusoutput('hg sum')

VERSION = output.split('\n')[0].split()[-1]

if VERSION == "tip":
    VERSION = getstatusoutput('hg branch')[1]
    if VERSION == 'default':
        t = getstatusoutput('hg sum')
        t = t[1].split('\n')[0].split()[1].split(':')[1]
        VERSION = 'default: %s' % t

VERSION = output.split('\n')[0].split()[-1]
setup(
    name="otto",
    version=VERSION,
    url='http://hg/qa/otto/',
    description="oTTo an Automation Library",
    author='Coraid QA Alumni',
    packages=find_packages('src'),
    package_dir={'': 'src'},
    install_requires=['setuptools',
                      'requests',
                      'simplejson',
                      'pyyaml',
                      'httplib2',
                      'docopt',
                      'jsonrpclib',
                      'paramiko>=1.15.1'],
    tests_require=['nose', 'mock'],
    zip_safe=False
)
