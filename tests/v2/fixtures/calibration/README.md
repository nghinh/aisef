# Calibration fixtures (RFC §9.1.1, WP-2.2)

One directory per probe kind and observation class, each with a `positive` fixture (the observable IS present:
the probe must observe SATISFIED) and a `negative` one (it is ABSENT: REFUTED). `request.json` is the probe input;
`checkout/` is the revision the probe looks at. Product fixtures only — no test file, no developer artefact.
