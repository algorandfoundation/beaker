The TAO of Boxes
----------------

If a `map` is required a box per key should be used
    - To know what the key to reference, ask the app to tell us what the key should be

A common pattern will likely be a user map


If a `list` is required it must be <128k to access the entire list
    - For an 8 byte element, this may contain 16000 elements
    - For a 32 byte element, this may contain 4000 elements
    - For a 128 byte element, this may contain 1000 elements






# Box Consensus params

 BoxFlatMinBalance = 0.002500
 BoxByteMinBalance = 0.000400

 MaxBoxSize = 4 * 8096
 MaxAppBoxReferences = 8
 BytesPerBoxReference = 1024

> Max box bytes accessible in 1 app call: 8k
> Max box bytes accessible in 16 app calls: 128k

# Box usage

```py
 name = Bytes("name")
 val = Bytes("val")
 size = Int(1)
 start = Int(1)

 BoxCreate(name, size) # Create a new box of size
 BoxDelete(name) # Delete box

 BoxExtract(name, start, size) # Get `size` bytes from box starting from `start`
 BoxReplace(name, start, val) # Overwrite whatever is in the box from start to len(val)
 BoxPut(name, val) # Write all contents of `val` to box starting from 0

 BoxGet(name) # Get the full contents of this box (will panic >4k)
 BoxLen(name) # Get the size of this box
```