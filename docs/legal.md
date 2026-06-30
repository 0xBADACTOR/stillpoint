# Legal notes

**This is not legal advice. Consult a lawyer in your jurisdiction before
deploying this tool.**

## Passive radio monitoring
- **United States**: Generally legal. No expectation-of-privacy ruling
  applies to broadcast MAC addresses or SSIDs. Some states restrict
  persistent tracking of individuals.
- **European Union**: Passive reception is legal. The GDPR applies to
  any *personal data* you store — MAC addresses paired with location
  history can arguably be personal data.
- **Australia**: Legal for personal protection. State laws vary on
  recording plates.

## License plate recognition
This is the legally sensitive piece. Many jurisdictions treat captured
plates as personal data:
- **EU/UK**: GDPR applies. You need a lawful basis (legitimate interest
  in personal safety is arguable but untested).
- **US**: No federal law against it for personal use, but some states
  restrict commercial ANPR use.
- **Australia**: Restricted under some state privacy acts.

## Recommendations
1. Default retention: **30 days**, then auto-purge.
2. Store plates **hashed** (SHA-256 with a salt) unless the operator
   explicitly opts in to plaintext.
3. Never publish a real detection database online.
4. Add a clear notice in the README that operators are responsible for
   compliance.

## Licensing & distribution
This project is licensed MIT and intended for **local, personal use**.
There is no hosted service, no cloud backend, and no reason to publish
a remote deployment. If you fork it, keep it local — exposing the
backend to the network would re-introduce all the surveillance risks
the design is meant to avoid.