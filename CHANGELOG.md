# Unreleased

<!--next-version-placeholder-->

# 0.4.1

 ## BugFix

 - Correct boxes dependency for Beaker (update sdk in pyproject.toml). (#136)
 - Properly handle "action" and "type" keys in decode_state (#130)
 - Add internal flag to handler config to prevent exposing internal methods (#153)

## Features

 - Adding support for creating multi page apps in an inner transaction (#133)
 - Allow multiple methods to specify on complete (#131)

 ## Housekeeping

 - Beaker productionisation, part 1 (moving tests, reconfigure CI, add tests for artifact output...) (#142)
 - Fix naming of example state keys changed dynamic -> reserved (#145)
 - Improved type annotations (#146, #147)








# 0.4.0 


- Add prefix to all `ReservedState` keys in order to prevent. 

    *WARNING: This is a BREAKING change* 

    This was done to nerf a "foot-gun" that might cause a contract author to overwrite the same key for separate `ReservedState` instances. It _can_ be overridden with another `keygen`, the previous behavior is provided with the `identity` keygen.
 

- Box Support

    The `storage` module of `beaker.lib` contains 2 new constructs to help use Boxes.

    - *List* : Allows a _list_ of some static abi type to be stored and accessed by index

    - *Mapping*: Allows a _map_ of some key to a specific box containing a certain data structure

    Example is available in `examples/boxen/application.py`
