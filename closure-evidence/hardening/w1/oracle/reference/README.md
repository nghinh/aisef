# Reference LedgerLock — the W1 oracle's independent calibration fixture

Written from `docs/requirements.md` alone (frozen; sha256 3a6a9995…). Never derived from, compared with, or corrected
against any AISEF-generated implementation. It exists so that the hidden oracle can be shown to (a) pass on a
requirement-conforming implementation and (b) turn red on each one-line mutant that removes one required behaviour
(`../calibrate.py`). Choices the requirements leave open are marked `choice:` in the source and listed in
`../../ORACLE-INDEPENDENCE.json`.
