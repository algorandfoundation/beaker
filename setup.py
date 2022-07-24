from distutils.core import setup

from setuptools import find_packages

setup(
    name="beaker",
    version="0.0.1dev",
    python_requires=">=3.10",
    packages=find_packages(),
    license="MIT",
    long_description=open("README.md").read(),
    package_data={"beaker": ["py.typed"]},
    install_requires=[
        "pyteal @ git+https://github.com/algorand/pyteal@master#egg=pyteal"
    ],
)
