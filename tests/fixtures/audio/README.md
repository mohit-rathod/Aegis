# Synthetic audio fixtures

Generated with Piper en_US-lessac-medium; mono int16 WAV at the voice's native rate. The runner resamples to 16kHz. These are synthetic fixtures, not representative human accent recordings.

- interruption.wav: 'Wait, wrong order.'
- question.wav: 'Where is my order A E G one zero zero one?'

The runner creates seeded short noise and silence in memory. Models are downloaded separately with pinned hashes. Sources and terms are in docs/voice-design.md.
