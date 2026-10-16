# Voice channel extension

Reserved for capture, VAD, end-of-utterance detection, barge-in, transcription, playback and recovery design. These capabilities are not implemented in this revision.

The extension point is the existing Runtime and SupportService. Transcribed input becomes a channel-independent Turn with channel=voice. The coordinator must reuse the session ID and trusted identity, generate a unique turn ID, call the shared guarded service, and play only its validated response. Interruption must invalidate old playback/generation IDs without bypassing session authorization or termination. GROQ_STT_MODEL is already available in the shared Settings model.
