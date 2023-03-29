Beaker
=========

.. image:: ../../beaker.png

.. module:: beaker


**Beaker** is a Python framework for building Smart Contracts on Algorand using `PyTeal <https://pyteal.readthedocs.io/en/stable/>`_.

.. note:: 
   This project is under active development


.. _installation:

Installation
------------

.. note::
    Beaker requires python 3.10 or higher

You may install from Pip

.. code-block:: console

    (.venv)$ pip install beaker-pyteal

Or from github directly

.. code-block:: console

    (.venv)$ pip install git+https://github.com/algorand-devrel/beaker


.. _hello_beaker:

Hello, Beaker 
-------------

.. literalinclude:: ../../examples/simple/hello.py



Usage
-----

Check out the :doc:`usage` section for further information.

See full examples `here <https://github.com/algorand-devrel/beaker/tree/master/examples>`_.



.. toctree::
    :hidden: 

    usage
    application
    lsig
    application_client
    sandbox
    state
    precompile
    decorators
    boxes
    migration


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
