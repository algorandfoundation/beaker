# TODOs

## house keeping

- [X] Install via pip

- [X] Documentation 

- [X] Unit Testing 

- [X] Better detection of app definition errors (cannot redeclare state keys, cannot declare over max schema)  

- [X] Use Dryrun for `read-only` methods

- [X] Automated testing of examples


### Utils

- Add Blobs from pyteal-utils for Global/Local state  (https://github.com/algorand-devrel/beaker/pull/41)

- Efficient List/Map of ABI types or `NamedTuple`/`Struct` with storage backing of Blob/Box

### Lsigs 

https://github.com/algorand-devrel/beaker/pull/33

- LSig Router based on `Args`

- LSig Template definition/parsing

- Verify hash of LSig logic (address) given input parameters and Template

### Contracts

- Trampoline - Adds method to deploy itself (w/ hook for other subroutine to call)

- Membership Token creation/validation

- Make OpUp on Public nets and hardcode it 
  

## features

- Add `Debug` mode using Dryrun/Simulate 

- Add Box state interface (take into account that callers need to know what box names they'll need access to)

- Migration, what if the app needs to change schema at some point? Create new app with updated schema but how do users migrate to new application?

- Automated Test Harness generation? no idea how to do this, graviton + dryruns?