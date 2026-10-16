# Evidence

Saved outputs are historical measurements, not generated claims about current provider quality. Each run identifies its test/provider/audio-device mode. Keep original logs unchanged; record new verification in a separate run directory.

- `archive/baseline-validation/`: original decision history.
- `runs/support-validation/`: earlier consolidated support checks.
- `runs/voice-validation/`: earlier synthetic speech/native audio/browser checks with explicit provider substitutes.
- `runs/cleanup-validation/`: cleanup regression, formatting, import/reference and packaging checks.

The presence of a fixture, script or 10,000-session benchmark is not proof of live Groq accuracy, physical microphone behavior or 10,000 concurrent voice calls.
