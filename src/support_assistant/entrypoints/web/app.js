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
  workletLoaded = false,
  ending = false;
let sid = sessionStorage.getItem("aegis-session") || null,
  sessionState = "active";
const nodes = new Set(),
  stopped = new Set(),
  bubbles = new Map(),
  pending = new Map();
let captureEnd = null,
  firstAudio = true,
  audioMeta = {};
function log(value) {
  $("events").textContent += `${new Date().toISOString()} ${value}\n`;
  if ($("events").textContent.length > 30000)
    $("events").textContent = $("events").textContent.slice(-24000);
  $("events").scrollTop = $("events").scrollHeight;
}
function send(packet) {
  if (socket?.readyState === WebSocket.OPEN)
    socket.send(JSON.stringify(packet));
}
function controls(connected) {
  for (const id of ["voice", "end", "disconnect", "text", "send"])
    $(id).disabled = !connected || ending;
  $("connect").disabled = connected;
}
function message(text, role = "assistant", id = null, citations = []) {
  $("messages").querySelector(".empty")?.remove();
  let entry = id && bubbles.get(id);
  if (!entry) {
    const node = document.createElement("div");
    node.className = `message ${role === "customer" ? "user" : role}`;
    const body = document.createElement("div"),
      note = document.createElement("small");
    node.append(body, note);
    $("messages").append(node);
    entry = { node, body, note };
    if (id) bubbles.set(id, entry);
  }
  entry.body.textContent = text;
  if (citations.length)
    entry.note.textContent = `Sources: ${[...new Set(citations.map((c) => (c.startsWith("tool-") ? "Order system" : c)))].join(", ")}`;
  else if (role === "human") entry.note.textContent = "Human support";
  $("messages").scrollTop = $("messages").scrollHeight;
  return entry;
}
function turnStatus(id, text) {
  const entry = bubbles.get(id + "-customer");
  if (entry) entry.note.textContent = text;
}
function metrics(data) {
  const labels = {
    endpoint_ms: "End-of-speech detection",
    queue_ms: "Queue wait",
    stt_ms: "Groq transcription",
    agent_ms: "Support processing",
    tts_first_chunk_ms: "TTS startup",
    end_to_text_server_ms: "Speech/send → text (server)",
    end_to_audio_server_ms: "Speech/send → first audio sent (server)",
    end_to_end_client_ms: "Speech/send → scheduled audio (browser)",
    end_to_text_client_ms: "Send → text (browser)",
  };
  $("metrics").textContent = "";
  const mode = document.createElement("div");
  mode.className = "metric-mode";
  mode.textContent = `${data.speaker === "human" ? "Human reply" : "Assistant response"} · ${data.provider_mode || "live pipeline"}`;
  $("metrics").append(mode);
  for (const [key, label] of Object.entries(labels)) {
    if (!Number.isFinite(data[key])) continue;
    const row = document.createElement("div");
    row.textContent = `${label}: ${(data[key] / 1000).toFixed(3)}s`;
    $("metrics").append(row);
  }
}
function setSessionState(state) {
  sessionState = state;
  $("session-state").textContent =
    state === "waiting_for_human"
      ? "Waiting for human"
      : state === "human_active"
        ? "Human support connected"
        : state === "terminated"
          ? "Ended"
          : "AI assistant";
  $("text").placeholder = ["waiting_for_human", "human_active"].includes(state)
    ? "Message the support team…"
    : "Type your question…";
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
  const raw = Uint8Array.from(atob(packet.pcm), (c) => c.charCodeAt(0)),
    view = new DataView(raw.buffer);
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
      audioMeta = { ...audioMeta, end_to_end_client_ms: value };
      $("latency").textContent =
        `Audio response: ${(value / 1000).toFixed(2)}s`;
      metrics(audioMeta);
      send({ type: "latency", value_ms: value, playback_id: playback });
      log(`end_of_input_to_scheduled_audio_ms=${value.toFixed(1)}`);
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
  $("voice").disabled = ending || socket?.readyState !== WebSocket.OPEN;
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
      message(
        "Audio transport is congested. Microphone stopped; please retry.",
        "notice",
      );
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
  controls(false);
  $("status").textContent = "Disconnected";
}
function retryText(id) {
  const job = pending.get(id);
  if (!job?.text || ending) return;
  send({
    type: "text",
    turn_id: id,
    text: job.text,
    submitted_at_ms: job.submitted,
  });
  turnStatus(id, "Retrying with the same turn ID…");
}
async function packetReceived(packet) {
  log(packet.type + (packet.state ? ` ${packet.state}` : ""));
  if (packet.type === "ready") {
    sid = packet.session_id;
    sessionStorage.setItem("aegis-session", sid);
    ending = false;
    controls(true);
    $("status").textContent = "Connected";
    $("session-info").textContent = `Session: ${sid}`;
    $("pipeline").textContent =
      `Provider mode: ${packet.provider_mode} · Groq Whisper → guarded Groq support → Piper`;
    clearInterval(heartbeat);
    heartbeat = setInterval(() => send({ type: "ping" }), 20000);
  } else if (packet.type === "history") {
    $("messages").textContent = "";
    bubbles.clear();
    for (const item of packet.messages)
      message(item.text, item.role, item.message_id);
    setSessionState(packet.state);
  } else if (packet.type === "chat_event") {
    message(packet.text, packet.role, packet.message_id);
  } else if (packet.type === "session_state") setSessionState(packet.state);
  else if (packet.type === "voice_ready") {
    if (!voiceRequested) {
      send({ type: "voice_stop" });
      return;
    }
    voice = true;
    $("voice").disabled = false;
    $("voice").textContent = "Stop voice";
    $("voice").classList.add("active");
    $("status").textContent = "Listening";
  } else if (packet.type === "state") $("status").textContent = packet.state;
  else if (packet.type === "turn_accepted") {
    if (!pending.has(packet.turn_id))
      pending.set(packet.turn_id, { channel: packet.channel });
    if (!bubbles.has(packet.turn_id + "-customer"))
      message(
        "Voice message accepted. Transcribing…",
        "customer",
        packet.turn_id + "-customer",
      );
    turnStatus(packet.turn_id, "Accepted; waiting for processing.");
  } else if (packet.type === "transcript") {
    message(packet.text, "customer", packet.turn_id + "-customer");
    turnStatus(packet.turn_id, "Processing…");
  } else if (packet.type === "response") {
    setSessionState(packet.session_state);
    if (packet.status !== "human_message")
      message(
        packet.answer,
        "assistant",
        packet.turn_id + "-assistant",
        packet.citations,
      );
    const job = pending.get(packet.turn_id),
      timing = { ...packet.timings };
    if (job?.submitted)
      timing.end_to_text_client_ms = performance.now() - job.submitted;
    metrics(timing);
    $("latency").textContent = Number.isFinite(timing.end_to_text_client_ms)
      ? `Text response: ${(timing.end_to_text_client_ms / 1000).toFixed(2)}s`
      : "Text response received; audio timing pending.";
    if (packet.superseded)
      turnStatus(packet.turn_id, "Handled; audio superseded by a later input.");
  } else if (packet.type === "turn_result") {
    turnStatus(
      packet.turn_id,
      packet.status === "completed"
        ? packet.reason === "human_message"
          ? "Delivered to human support."
          : "Handled."
        : `${packet.status}: ${packet.reason || ""}`,
    );
    if (packet.status === "failed") {
      message(
        "A turn failed explicitly; it was not silently discarded. Retry the message.",
        "notice",
      );
      const entry = bubbles.get(packet.turn_id + "-customer");
      if (entry && pending.get(packet.turn_id)?.text) {
        const button = document.createElement("button");
        button.textContent = "Retry message";
        button.onclick = () => retryText(packet.turn_id);
        entry.node.append(button);
      }
    }
  } else if (packet.type === "turn_rejected") {
    message(
      packet.message || "Conversation closed; message not accepted.",
      "notice",
    );
    turnStatus(packet.turn_id, "Not accepted; retry.");
  } else if (packet.type === "audio_start") {
    stopPlayback();
    playback = packet.playback_id;
    captureEnd = packet.captured_at_ms;
    firstAudio = true;
    audioMeta = {};
  } else if (packet.type === "audio_context") {
    if (packet.playback_id === playback)
      audioMeta = {
        ...packet.timings,
        speaker: packet.speaker,
        turn_id: packet.turn_id,
      };
  } else if (packet.type === "audio") await audio(packet);
  else if (packet.type === "metrics") {
    if (packet.playback_id === playback) {
      audioMeta = {
        ...packet,
        ...(Number.isFinite(audioMeta.end_to_end_client_ms)
          ? { end_to_end_client_ms: audioMeta.end_to_end_client_ms }
          : {}),
      };
      metrics(audioMeta);
    }
  } else if (packet.type === "audio_stop") {
    if (packet.playback_id === playback) stopPlayback(packet.playback_id);
  } else if (packet.type === "audio_end") {
    if (packet.playback_id === playback) playback = null;
  } else if (
    packet.type === "recovery" ||
    packet.type === "error" ||
    packet.type === "history_gap"
  ) {
    message(packet.message, "notice");
    if (packet.type === "error" && stream && !voice) await stopVoice();
  } else if (packet.type === "closed") {
    ending = true;
    sessionStorage.removeItem("aegis-session");
    sid = null;
    message(
      "The conversation has ended. Connect to start a new one.",
      "notice",
    );
    await disconnect();
    $("connect").disabled = false;
  }
}
$("connect").onclick = async () => {
  try {
    const token = $("token").value.trim();
    if (!token) throw Error("Enter your customer access token.");
    $("connect").disabled = true;
    if (sid) {
      const previous = await fetch(`/sessions/${sid}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (previous.ok) {
        const session = await previous.json();
        if (session.state === "terminated") sid = null;
      } else if (previous.status === 404) {
        sid = null;
        sessionStorage.removeItem("aegis-session");
      } else throw Error("Session authentication failed.");
    }
    if (!sid) {
      const result = await fetch("/sessions", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!result.ok)
        throw Error("Connection failed. Check the customer token and server.");
      sid = (await result.json()).session_id;
    }
    socket = new WebSocket(
      `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/sessions/${sid}/channel`,
    );
    socket.onopen = () => {
      send({ token });
      $("token").value = "";
    };
    // Serial packet processing avoids stale async audio handlers racing a stop event.
    let chain = Promise.resolve();
    socket.onmessage = (event) => {
      chain = chain
        .then(() => packetReceived(JSON.parse(event.data)))
        .catch((error) => {
          log(error.message);
          message(
            "An audio/channel error occurred. Reconnect if needed.",
            "notice",
          );
        });
    };
    socket.onclose = () => {
      clearInterval(heartbeat);
      stopVoice(false);
      controls(false);
      $("connect").disabled = false;
      $("status").textContent = "Disconnected";
    };
    socket.onerror = () =>
      message(
        "Connection failed. Reconnect to restore the transcript.",
        "notice",
      );
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
$("disconnect").onclick = disconnect;
$("end").onclick = async () => {
  ending = true;
  controls(false);
  await stopVoice(false);
  message("Ending the conversation…", "notice");
  send({ type: "end_conversation" });
};
$("composer").onsubmit = (event) => {
  event.preventDefault();
  const text = $("text").value.trim();
  if (!text || ending) return;
  const id = crypto.randomUUID();
  const submitted = performance.now();
  pending.set(id, { text, submitted, channel: "text" });
  while (pending.size > 120) pending.delete(pending.keys().next().value);
  message(text, "customer", id + "-customer");
  send({ type: "text", turn_id: id, text, submitted_at_ms: submitted });
  $("text").value = "";
};
window.addEventListener("pagehide", () => {
  stream?.getTracks().forEach((track) => track.stop());
  socket?.close();
});
