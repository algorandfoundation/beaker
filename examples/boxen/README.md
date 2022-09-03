The TAO of Boxes
----------------

If a `map` is required a box per key should be used
    - To know what the key to reference, ask the app to tell us what the key should be

A common pattern will likely be a user map


If a `list` is required it must be <128k to access the entire list
    - For an 8 byte element, this may contain 16000 elements
    - For a 32 byte element, this may contain 4000 elements
    - For a 128 byte element, this may contain 1000 elements





