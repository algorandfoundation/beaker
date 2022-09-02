from distutils.core import setup
from setuptools import find_packages


setup(
    name="beaker",
    version="0.1.6-alpha",
    python_requires=">=3.10",
    packages=find_packages(),
    license="MIT",
    long_description=open("README.md").read(),
    package_data={"beaker": ["py.typed"]},
    install_requires=["pyteal>=0.17.0", "py-algorand-sdk>=1.16.1"],
)
