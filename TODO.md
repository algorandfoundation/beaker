# TODOs

## random

- Use dryrun for `read-only` methods



## house keeping

- Deploy to pip

- Documentation 

- Unit/Integration Testing 

- Automated testing of examples

- Better detection of app definition errors (cannot redeclare state keys, cannot declare over max schema)  

## features

- Add `Debug` mode using Dryrun 

- Add Box state interface (take into account that callers need to know what box names they'll need access to)

- Migration, what if the app needs to change schema at some point? Create new app with updated schema but how do users migrate to new application?

- Automated Test Harness generation? no idea how to do this, graviton + dryruns?

### Utils

- Add Blobs from pyteal-utils for Global/Local state

- Efficient List/Map of ABI types or `Model` 

### Lsigs 

- LSig Router based on `Args`

- LSig Template definition

- Verify hash of LSig logic (address) given input parameters and Template

### Contracts

- Trampoline - Adds method to deploy itself (w/ hook for other subroutine to call)

- Membership Token creation/validation

- Other ARCs?