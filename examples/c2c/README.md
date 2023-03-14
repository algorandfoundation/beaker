Contract To Contract Example
-----------------------------


This demo is meant to show the use of both ``beaker.precompiled(...)`` for a ``beaker.Application`` and the ease of making Contract to Contract calls using `.method_signature()` on the ABI method created by applying app decorators (e.g. `@app.external`).

Additionally, this also shows the use of the `unfunded senders` feature since the sub application is never funded but over the course of a single transaction opts in to an asset, receives it, and closes out of the asset.
