from distutils.core import setup

from setuptools import find_packages

setup(
    name="beaker",
    version="0.0.1dev",
    packages=find_packages(),
    license="MIT",
    long_description=open("README.md").read(),
)
