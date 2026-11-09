/** 浏览器端 16k 单声道 WAV 录音，避免服务端依赖 ffmpeg。 */

export class WavRecorder {
  private context: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private processor: ScriptProcessorNode | null = null;
  private gain: GainNode | null = null;
  private chunks: Float32Array[] = [];
  private sampleRate = 48000;
  private startedAt = 0;

  get active() { return Boolean(this.context); }

  async start() {
    if (this.context) return;
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    this.context = new AudioContext();
    await this.context.resume();
    this.sampleRate = this.context.sampleRate;
    this.source = this.context.createMediaStreamSource(this.stream);
    this.processor = this.context.createScriptProcessor(4096, 1, 1);
    this.gain = this.context.createGain();
    this.gain.gain.value = 0;
    this.chunks = [];
    this.processor.onaudioprocess = (event) => {
      const channel = event.inputBuffer.getChannelData(0);
      this.chunks.push(new Float32Array(channel));
    };
    this.source.connect(this.processor);
    this.processor.connect(this.gain);
    this.gain.connect(this.context.destination);
    this.startedAt = performance.now();
  }

  async stop(): Promise<{ blob: Blob; duration: number }> {
    const elapsed = Math.max(1, Math.round((performance.now() - this.startedAt) / 1000));
    const sampleRate = this.sampleRate;
    this.processor?.disconnect();
    this.source?.disconnect();
    this.gain?.disconnect();
    this.stream?.getTracks().forEach((track) => track.stop());
    const context = this.context;
    this.context = null; this.stream = null; this.source = null; this.processor = null; this.gain = null;
    await context?.close().catch(() => undefined);
    const total = this.chunks.reduce((sum, chunk) => sum + chunk.length, 0);
    const merged = new Float32Array(total);
    let offset = 0;
    for (const chunk of this.chunks) { merged.set(chunk, offset); offset += chunk.length; }
    this.chunks = [];
    const pcm = resample(merged, sampleRate, 16000);
    return { blob: encodeWav(pcm, 16000), duration: elapsed };
  }
}

function resample(input: Float32Array, from: number, to: number): Float32Array {
  if (from === to) return input;
  const length = Math.max(1, Math.round(input.length * to / from));
  const output = new Float32Array(length);
  const ratio = from / to;
  for (let i = 0; i < length; i += 1) {
    const position = i * ratio;
    const index = Math.floor(position);
    const fraction = position - index;
    const first = input[index] || 0;
    const second = input[index + 1] || first;
    output[i] = first + (second - first) * fraction;
  }
  return output;
}

function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const write = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i));
  };
  write(0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  write(8, 'WAVE');
  write(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  write(36, 'data');
  view.setUint32(40, samples.length * 2, true);
  let offset = 44;
  for (let i = 0; i < samples.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
    offset += 2;
  }
  return new Blob([buffer], { type: 'audio/wav' });
}
