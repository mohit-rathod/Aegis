const $ = (id) => document.getElementById(id);
let socket,
  context,
  stream,
  capture,
  source,
  heartbeat,
  voice = false,
  playback = null,
  nextAt = 0;
let voiceRequested = false,
  micGeneration = 0,
  workletLoaded = false;
const nodes = new Set();
const stopped = new Set();
let captureEnd = null,
  firstAudio = true;
function log(value) {
  $("events").textContent += `${new Date().toISOString()} ${value}\n`;
  $("events").scrollTop = $("events").scrollHeight;
}
function send(packet) {
  if (socket?.readyState === WebSocket.OPEN)
    socket.send(JSON.stringify(packet));
}
function message(text, kind = "assistant", citations = []) {
  $("messages").querySelector(".empty")?.remove();
  const node = document.createElement("div");
  node.className = `message ${kind}`;
  node.textContent = text;
  if (citations.length) {
    const small = document.createElement("small");
    small.textContent = `Sources: ${[...new Set(citations.map((id) => (id.startsWith("tool-") ? "Order system" : id)))].join(", ")}`;
    node.append(small);
  }
  $("messages").append(node);
  $("messages").scrollTop = $("messages").scrollHeight;
}
function stopPlayback(identifier = playback) {
  if (identifier) stopped.add(identifier);
  while (stopped.size > 64) stopped.delete(stopped.values().next().value);
  for (const node of nodes) {
    node.onended = null;
    try {
      node.stop();
    } catch {}
    node.disconnect();
  }
  nodes.clear();
  nextAt = context?.currentTime || 0;
  playback = null;
  if (identifier) send({ type: "playback_stopped", playback_id: identifier });
}
async function audioContext() {
  if (!context) context = new AudioContext();
  await context.resume();
  return context;
}
async function audio(packet) {
  if (
    !voice ||
    packet.playback_id !== playback ||
    stopped.has(packet.playback_id)
  )
    return;
  const ctx = await audioContext();
  if (packet.playback_id !== playback) return;
  const raw = Uint8Array.from(atob(packet.pcm), (c) => c.charCodeAt(0));
  const view = new DataView(raw.buffer);
  const buffer = ctx.createBuffer(1, raw.byteLength / 2, packet.sample_rate),
    samples = buffer.getChannelData(0);
  for (let i = 0; i < samples.length; i++)
    samples[i] = view.getInt16(i * 2, true) / 32768;
  const node = ctx.createBufferSource();
  node.buffer = buffer;
  node.connect(ctx.destination);
  const when = Math.max(ctx.currentTime + 0.015, nextAt);
  nextAt = when + buffer.duration;
  nodes.add(node);
  node.onended = () => {
    nodes.delete(node);
    node.disconnect();
    send({
      type: "audio_ack",
      playback_id: packet.playback_id,
      sequence: packet.sequence,
    });
  };
  if (firstAudio) {
    firstAudio = false;
    if (captureEnd !== null) {
      const value =
        performance.now() + (when - ctx.currentTime) * 1000 - captureEnd;
      $("latency").textContent = `Response: ${(value / 1000).toFixed(2)}s`;
      send({ type: "latency", value_ms: value, playback_id: playback });
      log(`capture_to_scheduled_audio_ms=${value.toFixed(1)}`);
    }
  }
  node.start(when);
}
async function stopVoice(notify = true) {
  voice = false;
  voiceRequested = false;
  micGeneration++;
  capture?.disconnect();
  source?.disconnect();
  stream?.getTracks().forEach((track) => track.stop());
  capture = null;
  source = null;
  stream = null;
  stopPlayback();
  $("voice").textContent = "Start voice";
  $("voice").classList.remove("active");
  $("voice").disabled = socket?.readyState !== WebSocket.OPEN;
  if (notify) send({ type: "voice_stop" });
}
async function startVoice() {
  if (!navigator.mediaDevices?.getUserMedia)
    throw Error("Microphone requires localhost or HTTPS.");
  const request = ++micGeneration;
  voiceRequested = true;
  $("voice").disabled = true;
  const ctx = await audioContext();
  if (!workletLoaded) {
    await ctx.audioWorklet.addModule("/assets/capture-worklet.js");
    workletLoaded = true;
  }
  const acquired = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });
  if (request !== micGeneration || socket?.readyState !== WebSocket.OPEN) {
    acquired.getTracks().forEach((track) => track.stop());
    return;
  }
  stream = acquired;
  source = ctx.createMediaStreamSource(stream);
  capture = new AudioWorkletNode(ctx, "aegis-capture");
  capture.port.onmessage = (event) => {
    if (!voice || socket?.readyState !== WebSocket.OPEN) return;
    if (socket.bufferedAmount > 65536) {
      log("Audio transport congested; stopping microphone.");
      stopVoice();
      return;
    }
    const packet = new ArrayBuffer(1032);
    new DataView(packet).setFloat64(0, performance.now(), true);
    new Uint8Array(packet, 8).set(new Uint8Array(event.data));
    socket.send(packet);
  };
  source.connect(capture);
  capture.connect(ctx.destination);
  send({ type: "voice_start" });
}
async function disconnect() {
  clearInterval(heartbeat);
  await stopVoice(false);
  send({ type: "close" });
  socket?.close();
  $("status").textContent = "Disconnected";
  $("connect").disabled = false;
  for (const id of ["voice", "end", "text", "send"]) $(id).disabled = true;
}
$("connect").onclick = async () => {
  try {
    const token = $("token").value.trim();
    if (!token) throw Error("Enter your demo access token.");
    $("connect").disabled = true;
    const result = await fetch("/sessions", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!result.ok)
      throw Error("Connection failed. Check your customer token and server.");
    const session = await result.json();
    socket = new WebSocket(
      `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/sessions/${session.session_id}/channel`,
    );
    socket.onopen = () => {
      send({ token });
      $("token").value = "";
    };
    socket.onmessage = async (event) => {
      const packet = JSON.parse(event.data);
      log(packet.type + (packet.state ? ` ${packet.state}` : ""));
      if (packet.type === "ready") {
        for (const id of ["voice", "end", "text", "send"])
          $(id).disabled = false;
        $("status").textContent = "Connected";
        message(
          "Welcome to Aegis support. Type a message or start voice.",
          "notice",
        );
        heartbeat = setInterval(() => send({ type: "ping" }), 20000);
      } else if (packet.type === "voice_ready") {
        if (!voiceRequested) {
          send({ type: "voice_stop" });
          return;
        }
        voice = true;
        $("voice").disabled = false;
        $("voice").textContent = "Stop voice";
        $("voice").classList.add("active");
        $("status").textContent = "Listening";
      } else if (packet.type === "state")
        $("status").textContent = packet.state;
      else if (packet.type === "transcript") message(packet.text, "user");
      else if (packet.type === "response")
        message(
          packet.answer + (packet.superseded ? " (interrupted)" : ""),
          "assistant",
          packet.citations,
        );
      else if (packet.type === "audio_start") {
        stopPlayback();
        playback = packet.playback_id;
        captureEnd = packet.captured_at_ms;
        firstAudio = true;
      } else if (packet.type === "audio") await audio(packet);
      else if (packet.type === "audio_stop") {
        if (packet.playback_id === playback) stopPlayback(packet.playback_id);
      } else if (packet.type === "audio_end") {
        if (packet.playback_id === playback) playback = null;
      } else if (packet.type === "recovery" || packet.type === "error") {
        message(packet.message, "notice");
        if (packet.type === "error" && stream && !voice) await stopVoice();
      } else if (packet.type === "closed") {
        message("This support session has ended.", "notice");
        await disconnect();
      }
    };
    socket.onclose = () => {
      clearInterval(heartbeat);
      stopVoice(false);
      $("status").textContent = "Disconnected";
      $("connect").disabled = false;
      for (const id of ["voice", "end", "text", "send"]) $(id).disabled = true;
    };
    socket.onerror = () =>
      message("The connection failed. Please reconnect.", "notice");
  } catch (error) {
    message(error.message, "notice");
    $("connect").disabled = false;
  }
};
$("voice").onclick = async () => {
  try {
    if (voice || stream) await stopVoice();
    else await startVoice();
  } catch (error) {
    await stopVoice();
    message(error.message, "notice");
  }
};
$("end").onclick = disconnect;
$("composer").onsubmit = (event) => {
  event.preventDefault();
  const text = $("text").value.trim();
  if (text) {
    send({ type: "text", text });
    $("text").value = "";
  }
};
window.addEventListener("pagehide", () => {
  stream?.getTracks().forEach((track) => track.stop());
  socket?.close();
});
