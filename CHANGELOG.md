# Unreleased


- Add prefix to all `ReservedState` keys in order to prevent. 

    *WARNING: This is a BREAKING change* 

    This was done to nerf a "foot-gun" that might cause a contract author to overwrite the same key for separate `ReservedState` instances. It _can_ be overridden with another `keygen`, the previous behavior is provided with the `identity` keygen.
 

- Box Support

    The `storage` module of `beaker.lib` contains 2 new constructs to help use Boxes.

    - *List* : Allows a _list_ of some static abi type to be stored and accessed by index

    - *Mapping*: Allows a _map_ of some key to a specific box containing a certain data structure

    Example is available in `examples/boxen/application.py`
