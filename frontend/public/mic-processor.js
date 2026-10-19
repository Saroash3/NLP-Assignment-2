/**
 * AudioWorklet (runs on the browser's audio thread): turns the microphone into 16 kHz 16-bit
 * PCM -- what the server's VAD and Whisper expect -- and posts it in 1024-sample (64 ms) chunks.
 *
 * Normally the AudioContext itself already runs at 16 kHz (the browser's own high-quality
 * resampler did the work) and `step` is 1: samples pass straight through. Only if the browser
 * refused a 16 kHz context do we downsample here, by averaging each group of input samples
 * ("box filter"). That average is a simple low-pass filter: plain interpolation without it
 * folded high-frequency noise back into the speech band and hurt recognition of real mics.
 */
const TARGET_RATE = 16000;
const CHUNK = 1024;

class MicProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.step = sampleRate / TARGET_RATE; // `sampleRate` is a global inside a worklet; 1 = no resampling
    this.pos = 0; // input samples gathered toward the next output sample
    this.sum = 0;
    this.count = 0;
    this.out = new Int16Array(CHUNK);
    this.n = 0;
  }

  process(inputs) {
    const input = inputs[0] && inputs[0][0]; // first channel = mono
    if (!input) return true;
    for (let i = 0; i < input.length; i++) {
      this.sum += input[i];
      this.count += 1;
      this.pos += 1;
      if (this.pos >= this.step) {
        this.pos -= this.step;
        const sample = this.sum / this.count; // average of the samples this output covers
        this.sum = 0;
        this.count = 0;
        this.out[this.n++] = Math.max(-1, Math.min(1, sample)) * 0x7fff;
        if (this.n === CHUNK) {
          this.port.postMessage(this.out.buffer, [this.out.buffer]); // transfer, no copy
          this.out = new Int16Array(CHUNK);
          this.n = 0;
        }
      }
    }
    return true; // keep the processor alive
  }
}

registerProcessor("mic-processor", MicProcessor);
