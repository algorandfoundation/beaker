Contract To Contract Example
-----------------------------


This demo is meant to show the use of both a ``Precompile`` for an ``Application`` and the ease of making Contract to Contract calls using the method signature provided by the ``Application`` method using the `get_method_signature` method provided by `Beaker`.

Additionally, this also shows the use of the `unfunded senders` feature since the sub application is never funded but over the course of a single transaction opts in to an asset, receives it, and closes out of the asset.
