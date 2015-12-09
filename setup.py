#!/bin/env python2.7

from setuptools import setup, find_packages

setup(
    name="otto",
    version="1.4.5",
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
