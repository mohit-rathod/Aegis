const $ = (id) => document.getElementById(id);
let token = "",
  selected = null,
  timer = null,
  busy = false;
async function api(path, method = "GET", body) {
  const controller = new AbortController(),
    timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(path, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok)
      throw Error(
        typeof data.detail === "string"
          ? data.detail
          : `Request failed (${response.status})`,
      );
    return data;
  } finally {
    clearTimeout(timeout);
  }
}
function textNode(tag, text, className = "") {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
}
async function refresh() {
  if (!token || busy) return;
  busy = true;
  try {
    const rows = await api("/admin/support-requests");
    $("inbox").textContent = "";
    if (!rows.length)
      $("inbox").append(
        textNode(
          "p",
          "No pending handoffs. The chat box appears when a customer is escalated.",
          "muted",
        ),
      );
    for (const row of rows) {
      const button = textNode(
        "button",
        `${row.customer_id} · ${row.status} · ${row.request_id}`,
        "ticket",
      );
      button.onclick = () => {
        selected = row.request_id;
        refreshSelected();
      };
      $("inbox").append(button);
    }
    if (!selected && rows.length) selected = rows[0].request_id;
    if (selected) await refreshSelected();
    $("admin-status").textContent = "Connected";
  } catch (error) {
    $("admin-status").textContent = error.message;
  } finally {
    busy = false;
  }
}
async function refreshSelected() {
  if (!selected) return;
  const detail = await api(`/admin/support-requests/${selected}`);
  const ticket = detail.request,
    session = detail.session;
  $("human-chat").hidden = false;
  $("ticket-title").textContent = `${ticket.request_id} · ${ticket.status}`;
  const summary = ticket.summary || {};
  $("handoff-summary").textContent = "";
  $("handoff-summary").append(
    textNode("h3", "Handoff summary"),
    textNode("p", summary.overview || "No earlier transcript."),
    textNode("h3", "Help requested"),
    textNode(
      "p",
      summary.help_needed ||
        ticket.customer_statement ||
        "Ask the customer for details.",
    ),
  );
  if (summary.preceding_customer_requests?.length)
    $("handoff-summary").append(
      textNode(
        "p",
        "Earlier customer requests: " +
          summary.preceding_customer_requests.join(" | "),
      ),
    );
  if (summary.verified_order_id)
    $("handoff-summary").append(
      textNode("p", "Verified order context: " + summary.verified_order_id),
    );
  const nearBottom =
    $("admin-messages").scrollHeight -
      $("admin-messages").scrollTop -
      $("admin-messages").clientHeight <
    60;
  $("admin-messages").textContent = "";
  for (const item of session.history) {
    const node = textNode(
      "div",
      item.text,
      `message ${item.role === "customer" ? "user" : item.role}`,
    );
    node.append(textNode("small", item.role));
    $("admin-messages").append(node);
  }
  if (nearBottom)
    $("admin-messages").scrollTop = $("admin-messages").scrollHeight;
  const current = session.support_request_id === selected;
  const active =
    current && session.state === "human_active" && ticket.status === "active";
  $("claim").disabled = !current || session.state !== "waiting_for_human";
  for (const id of ["admin-text", "admin-send", "resolve", "resolution"])
    $(id).disabled = !active;
}
$("admin-connect").onclick = async () => {
  token = $("admin-token").value.trim();
  if (!token) return;
  $("admin-token").value = "";
  try {
    await api("/admin/support-requests");
    $("admin-connect").disabled = true;
    $("admin-signout").disabled = false;
    $("arm-fault").disabled = false;
    await refresh();
    clearInterval(timer);
    timer = setInterval(refresh, 1000);
  } catch (error) {
    token = "";
    $("admin-status").textContent = error.message;
  }
};
$("admin-signout").onclick = () => {
  clearInterval(timer);
  token = "";
  selected = null;
  $("human-chat").hidden = true;
  $("inbox").textContent = "";
  $("admin-connect").disabled = false;
  $("admin-signout").disabled = true;
  $("arm-fault").disabled = true;
  $("admin-status").textContent = "Signed out";
};
$("claim").onclick = async () => {
  try {
    await api(`/admin/support-requests/${selected}/claim`, "POST");
    await refreshSelected();
  } catch (error) {
    $("admin-status").textContent = error.message;
  }
};
let pendingReply = null;
$("admin-composer").onsubmit = async (event) => {
  event.preventDefault();
  const text = $("admin-text").value.trim();
  if (!text || !selected) return;
  if (
    !pendingReply ||
    pendingReply.text !== text ||
    pendingReply.ticket !== selected
  )
    pendingReply = { ticket: selected, text, message_id: crypto.randomUUID() };
  $("admin-send").disabled = true;
  try {
    await api(`/admin/support-requests/${selected}/messages`, "POST", {
      text: pendingReply.text,
      message_id: pendingReply.message_id,
    });
    pendingReply = null;
    $("admin-text").value = "";
    await refreshSelected();
  } catch (error) {
    $("admin-status").textContent =
      error.message + " — retry keeps the same message ID.";
  } finally {
    $("admin-send").disabled = false;
  }
};
$("resolve").onclick = async () => {
  const resolution = $("resolution").value.trim();
  try {
    $("resolve").disabled = true;
    await api(`/admin/support-requests/${selected}/resolve`, "POST", {
      resolution,
    });
    $("resolution").value = "";
    await refresh();
  } catch (error) {
    $("admin-status").textContent = error.message;
    $("resolve").disabled = false;
  }
};
$("arm-fault").onclick = async () => {
  try {
    const sid = $("fault-session").value.trim();
    if (!/^[0-9a-f]{32}$/.test(sid))
      throw Error("Enter a valid customer session ID.");
    const data = await api(`/admin/sessions/${sid}/fault`, "POST", {
      kind: $("fault-kind").value,
    });
    $("fault-status").textContent =
      `Armed ${data.armed} once. The next matching stage will fail; observe the customer page and terminal logs.`;
  } catch (error) {
    $("fault-status").textContent = error.message;
  }
};
window.addEventListener("pagehide", () => {
  clearInterval(timer);
  token = "";
});
