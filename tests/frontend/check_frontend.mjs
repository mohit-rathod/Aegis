// Dependency-free transport/audio contract checks. This is not a physical-browser test.
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
const root = new URL(
  "../../src/support_assistant/entrypoints/web/",
  import.meta.url,
);
class Element {
  constructor() {
    this.value = "";
    this.textContent = "";
    this.children = [];
    this.disabled = false;
    this.classList = { add() {}, remove() {} };
  }
  append(node) {
    this.children.push(node);
  }
  querySelector() {
    return null;
  }
  remove() {}
}
const elements = new Map();
const document = {
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, new Element());
    return elements.get(id);
  },
  createElement() {
    return new Element();
  },
};
let socket, worklet;
const sources = [];
class WebSocket {
  static OPEN = 1;
  constructor() {
    socket = this;
    this.readyState = 1;
    this.bufferedAmount = 0;
    this.sent = [];
  }
  send(data) {
    this.sent.push(data);
  }
  close() {
    this.readyState = 3;
    this.onclose?.();
  }
}
class AudioContext {
  constructor() {
    this.currentTime = 0;
    this.destination = {};
    this.audioWorklet = { async addModule() {} };
  }
  async resume() {}
  createMediaStreamSource() {
    return { connect() {}, disconnect() {} };
  }
  createBuffer(channels, length, rate) {
    return {
      duration: length / rate,
      getChannelData() {
        return new Float32Array(length);
      },
    };
  }
  createBufferSource() {
    const node = {
      connect() {},
      disconnect() {},
      stop() {
        this.stopped = true;
      },
      start() {
        this.started = true;
      },
    };
    sources.push(node);
    return node;
  }
}
class AudioWorkletNode {
  constructor() {
    worklet = this;
    this.port = {};
  }
  connect() {}
  disconnect() {}
}
const context = vm.createContext({
  document,
  WebSocket,
  AudioContext,
  AudioWorkletNode,
  console,
  performance,
  Uint8Array,
  Float32Array,
  Int16Array,
  ArrayBuffer,
  DataView,
  Set,
  Date,
  Math,
  atob,
  location: { protocol: "http:", host: "localhost:8000" },
  navigator: {
    mediaDevices: {
      async getUserMedia() {
        return {
          getTracks() {
            return [{ stop() {} }];
          },
        };
      },
    },
  },
  window: { addEventListener() {} },
  setInterval() {
    return 1;
  },
  clearInterval() {},
  async fetch() {
    return {
      ok: true,
      async json() {
        return { session_id: "a".repeat(32) };
      },
    };
  },
});
vm.runInContext(fs.readFileSync(new URL("app.js", root), "utf8"), context);
document.getElementById("token").value = "demo-a";
await elements.get("connect").onclick();
socket.onopen();
assert.equal(JSON.parse(socket.sent[0]).token, "demo-a");
await socket.onmessage({ data: JSON.stringify({ type: "ready" }) });
elements.get("text").value = "Where is my order?";
elements.get("composer").onsubmit({ preventDefault() {} });
assert.equal(JSON.parse(socket.sent.at(-1)).type, "text");
await elements.get("voice").onclick();
await socket.onmessage({ data: JSON.stringify({ type: "voice_ready" }) });
worklet.port.onmessage({ data: new ArrayBuffer(1024) });
assert.equal(socket.sent.at(-1).byteLength, 1032);
await socket.onmessage({
  data: JSON.stringify({
    type: "audio_start",
    playback_id: "p1",
    captured_at_ms: performance.now() - 1000,
  }),
});
const packet = {
  type: "audio",
  playback_id: "p1",
  sequence: 0,
  sample_rate: 16000,
  pcm: Buffer.alloc(2048).toString("base64"),
};
await socket.onmessage({ data: JSON.stringify(packet) });
assert.equal(sources.length, 1);
assert.ok(sources[0].started);
await socket.onmessage({
  data: JSON.stringify({ type: "audio_stop", playback_id: "p1" }),
});
assert.ok(sources[0].stopped);
await socket.onmessage({ data: JSON.stringify(packet) });
assert.equal(sources.length, 1, "Stale audio must not create a source");
assert.ok(
  socket.sent.some(
    (p) => typeof p === "string" && JSON.parse(p).type === "playback_stopped",
  ),
);
let Processor;
const frames = [];
const workletContext = vm.createContext({
  sampleRate: 48000,
  Int16Array,
  Math,
  AudioWorkletProcessor: class {
    constructor() {
      this.port = {
        postMessage(frame) {
          frames.push(frame);
        },
      };
    }
  },
  registerProcessor(name, cls) {
    Processor = cls;
  },
});
vm.runInContext(
  fs.readFileSync(new URL("capture-worklet.js", root), "utf8"),
  workletContext,
);
const processor = new Processor();
for (let i = 0; i < 20; i++)
  processor.process([[new Float32Array(128).fill(0.5)]], []);
assert.ok(frames.length > 0);
assert.equal(frames[0].byteLength, 1024);
assert.ok(new Int16Array(frames[0])[0] > 15000);
const precise = new Processor();
const beforeFrames = frames.length;
for (let i = 0; i < 375; i++)
  precise.process([[new Float32Array(128).fill(0.5)]], []);
assert.equal(
  (frames.length - beforeFrames) * 512 + precise.index,
  16000,
  "Resampling must not drift at 48kHz",
);
console.log(
  "PASS: text send, auth, mic framing/resampling, playback stop acknowledgment, stale audio rejection.",
);
