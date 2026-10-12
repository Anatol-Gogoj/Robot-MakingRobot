# ADR-0003: An unreadable `procedure_result` means unverified, not failed
Status: Accepted; Date: 2026-08-11 (handoff decision 7); Scope: `spincoater.cpp` boot and `doIndexHome()` index-search checks
Context: Reaching IDLE proves nothing about an index search, because the axis returns to IDLE after both success and failure (#43). `axis0.procedure_result` is the only discriminator. Not every ODrive firmware may expose it, and a corrupted reply must not be read as a value (#44).
Decision: `getProcedureResult()` returns -1 when the property cannot be read or parsed. Callers treat -1 as UNVERIFIED: they print a `WARN:` line and carry on (`spincoater.cpp:215-224` at boot, and the `doIndexHome()` check after the search). Only a successfully read non-zero value fails the home.
Rejected: Treating unreadable as failed: an ODrive firmware without the property would brick a working machine
Rejected: Treating unreadable as success without saying so: hides exactly the evidence #43 was about
Consequences: Easier: older ODrive firmware keeps working. Harder: an unreadable result leaves the home unproven, so the operator must read the `WARN:` line, which neither UI highlights yet (#47).
Revisit if: the ODrive firmware is pinned to a version known to expose `procedure_result`.
