// Reblock and resample actual device rate to 512 mono samples at 16kHz.
class Capture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.samples = [];
    this.position = 0;
    this.frame = new Int16Array(512);
    this.index = 0;
  }
  process(inputs, outputs) {
    const input = inputs[0]?.[0];
    if (!input) return true;
    for (const sample of input) this.samples.push(sample);
    const step = sampleRate / 16000;
    while (this.position + 1 < this.samples.length) {
      const i = Math.floor(this.position),
        f = this.position - i;
      const value = this.samples[i] * (1 - f) + this.samples[i + 1] * f;
      this.frame[this.index++] = Math.round(
        Math.max(-1, Math.min(1, value)) * 32767,
      );
      this.position += step;
      if (this.index === 512) {
        const frame = this.frame;
        this.port.postMessage(frame.buffer, [frame.buffer]);
        this.frame = new Int16Array(512);
        this.index = 0;
      }
    }
    const consumed = Math.min(
      Math.floor(this.position),
      this.samples.length - 1,
    );
    this.samples.splice(0, consumed);
    this.position -= consumed;
    // The output is silent; microphone audio must never be routed to speakers.
    return true;
  }
}
registerProcessor("aegis-capture", Capture);
