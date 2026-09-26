# Measurement honesty (always on)

- Every number in the app comes from a real measurement stored in SQLite.
  No placeholders, no "example" values, no mocked telemetry in app code.
  Fake/synthetic numbers are allowed ONLY inside tests/.
- If a sensor or metric is unavailable: store NULL, show "not available",
  and explain why in one short sentence (e.g. "discharge rate reads 0 while charging").
- Always record provider_used from session.get_providers()[0]; exclude runs
  where it differs from the requested provider.
- Never extrapolate beyond 2x the largest measured model size without
  labelling the value "extrapolated".
- When you report results to me, paste the actual command output. Never
  summarise numbers you did not just see in output.
- If I ask for something that would require faking data, say so and
  propose an honest alternative.
