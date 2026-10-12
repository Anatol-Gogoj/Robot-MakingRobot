# ADR-0006: Over Web Serial the Touch UI reconnects by itself and the Controller does not
Status: Accepted; Date: 2026-08-14 (handoff decision 11); Scope: `RMR_Controller.html`, `RMR_Touch.html`, Web Serial transport
Context: The Mega's USB link drops and re-enumerates now and then, and the operator panel should recover without a person. The Controller page is the one left open on the dev machine while firmware is uploaded.
Decision: In Web Serial mode the Touch UI retries the port after a read error, with exponential backoff and a bounded number of attempts (`attemptReconnect()`, `MAX_RECONNECT` in `RMR_Touch.html`); the Controller does not, and the operator reconnects it by hand. In Pi-bridge (WebSocket) mode both pages reconnect to the bridge, because the bridge, not the browser, owns the port.
Rejected: Auto-reconnect in the Controller: it would race avrdude for the port during an upload
Consequences: Easier: uploads from the Controller's machine are not interrupted, and the panel heals itself. Harder: the asymmetry looks like a bug; this record exists so it is not "fixed".
Revisit if: uploads move off the machine that runs the Controller.
