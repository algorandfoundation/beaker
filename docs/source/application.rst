Application
============

.. module:: beaker.application

This is the base class that all Beaker Applications should inherit from.

This should _not_ be initialized directly.

.. autoclass:: Application


    .. automethod:: application_spec

    .. automethod:: initialize_application_state
    .. automethod:: initialize_account_state

    Override the create method define custom behavior

    .. automethod:: create



