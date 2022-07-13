from distutils.core import setup

from setuptools import find_packages

setup(
    name="beaker",
    version="0.0.1dev",
    packages=find_packages(),
    license="MIT",
    long_description=open("README.md").read(),
    install_requires=[
        "pyteal @ git+https://github.com/algorand/pyteal@feature/abi#egg=pyteal"
    ],
)
