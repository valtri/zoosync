# -*- coding: utf-8

# Always prefer setuptools over distutils
from setuptools import setup, find_packages
# To use a consistent encoding
from codecs import open
from os import path

import zoosync

here = path.abspath(path.dirname(__file__))

with open(path.join(here, 'DESCRIPTION.rst'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='zoosync',

    version=zoosync.__version__,

    description='Zookeeper service discovery',
    long_description=long_description,

    url='https://github.com/valtri/zoosync',

    author='František Dvořák',
    author_email='valtri@civ.zcu.cz',

    license='MIT',

    classifiers=[
        'Development Status :: 3 - Alpha',

        'Intended Audience :: Information Technology',
        'Topic :: System :: Distributed Computing',

        'License :: OSI Approved :: MIT License',

        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
    ],

    keywords='service-discovery zookeeper cloud',

    packages=find_packages(exclude=['contrib', 'docs', 'tests*']),

    install_requires=['kazoo'],

    package_data={
        'zoosync': [
            'zoosync.1',
            'scripts/zoosync.service',
            'scripts/zoosync.sh',
        ],
    },

    entry_points={
        'console_scripts': [
            'zoosync=zoosync.zoosync:main',
        ],
    },

    test_suite='tests.test_zoosync.suite'
)
