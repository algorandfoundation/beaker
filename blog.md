Hello, Beaker
--------------

# Intro

devving scs in pyteal for algorand comes with glass chewing

general code org:
    how do i organize? method for approval/clear? return Cond boooo
state stuff 
    how to i track the state for my app? declare consts for keys and re-use those? what type are they? how do i remember
    which when i create the app?
deploying/calling
    creating and signing transactions manually
    call methods with imported json contract and pass args as list with no context
debugging
    pc=xxx PC LOAD LETTER?!
testing
    writing tests not ez, common patterns could make test tooling ez 



# ABI

The abi makes it easier with standards for types and calling methods
link to blog
link to arc


# Pyteal ABI

Pyteal improves situation w/ abi types, abi methods and router func... 
link to blog 
link to docs


# Beaker

Under the covers beaker uses all the great stuff from pyteal abi

code org: Beaker provides standard way to organize code with inheritence 

State stuff: declare state vars directly in application 

deploying/calling: app client makes it ez to deploy/call

testing: initially just balance helpers

debugging: wraping pc=xxx messages in LogicError with trace from _ACTUAL_ source teal
