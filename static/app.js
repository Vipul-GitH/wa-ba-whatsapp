const currentUser = document.querySelector(".appShell")?.dataset.currentUserName || "Staff";
const appShell = document.querySelector(".appShell");
const currentUserId = Number(appShell?.dataset.currentUserId || 0);
const closureTypes = ["Report", "Invoice", "Lead", "Complaint", "Home Collection", "Doctor", "Pickup", "Other"];

const state = {
  activeMobile: "",
  activeQueue: "All Chats",
  allRows: [],
  rows: [],
  userOptions: [],
  searchTimer: null,
  showQueues: true,
  showChatList: true,
  drawerMode: "",
  selectedFile: null,
};

const els = {
  toast: document.querySelector("#toast"),
  breachCount: document.querySelector("#breachCount"),
  topStateChip: document.querySelector("#topStateChip"),
  queueNav: document.querySelector("#queueNav"),
  activeQueueLabel: document.querySelector("#activeQueueLabel"),
  conversationList: document.querySelector("#conversationList"),
  messages: document.querySelector("#messages"),
  activeMobile: document.querySelector("#activeMobile"),
  activeSummary: document.querySelector("#activeSummary"),
  ownerLine: document.querySelector("#ownerLine"),
  slaStatus: document.querySelector("#slaStatus"),
  takenAt: document.querySelector("#takenAt"),
  typeSelect: document.querySelector("#typeSelect"),
  saveTypeBtn: document.querySelector("#saveTypeBtn"),
  takeBtn: document.querySelector("#takeBtn"),
  closeBtn: document.querySelector("#closeBtn"),
  replyForm: document.querySelector("#replyForm"),
  replyText: document.querySelector("#replyText"),
  sendBtn: document.querySelector("#sendBtn"),
  fileInput: document.querySelector("#fileInput"),
  emojiBtn: document.querySelector("#emojiBtn"),
  attachBtn: document.querySelector("#attachBtn"),
  dictBtn: document.querySelector("#dictBtn"),
  hubGrid: document.querySelector("#hubGrid"),
  toggleQueues: document.querySelector("#toggleQueues"),
  toggleChatList: document.querySelector("#toggleChatList"),
  searchInput: document.querySelector("#searchInput"),
  dateInput: document.querySelector("#dateInput"),
  tagStrip: document.querySelector("#tagStrip"),
  tagNote: document.querySelector("#tagNote"),
  contactName: document.querySelector("#contactName"),
  contactContext: document.querySelector("#contactContext"),
  leadList: document.querySelector("#leadList"),
  ticketList: document.querySelector("#ticketList"),
  homeCollectionList: document.querySelector("#homeCollectionList"),
  auditSummary: document.querySelector("#auditSummary"),
  assistPanel: document.querySelector("#assistPanel"),
  drawerBackdrop: document.querySelector("#drawerBackdrop"),
  drawerTitle: document.querySelector("#drawerTitle"),
  drawerQuestion: document.querySelector("#drawerQuestion"),
  drawerFields: document.querySelector("#drawerFields"),
  drawerClose: document.querySelector("#drawerClose"),
  drawerCancel: document.querySelector("#drawerCancel"),
  drawerSave: document.querySelector("#drawerSave"),
  actionButtons: document.querySelectorAll("[data-drawer]"),
};

const replyDictionary = [
  ["Report", "ripot, riport, report query"],
  ["Invoice", "invois, bill, payment"],
  ["Booking", "buking, appointment, slot"],
  ["Home Collection", "home sample pickup"],
  ["Fasting", "fasting sample"],
  ["Sample", "sampal, blood sample"],
  ["CBC", "Complete Blood Count"],
  ["LFT", "Liver Function Test"],
  ["KFT", "Kidney Function Test"],
  ["HbA1c", "diabetes average sugar"],
  ["TSH", "thyroid screening"],
  ["Kripya registered mobile number share karein.", "polite Hinglish"],
  ["Report check karke update kar rahe hain.", "report desk response"],
  ["Sample collection slot confirm kar denge.", "home collection"],
];

const professionalEmojis = [
  ["ðŸ™", "Polite request"],
  ["âœ…", "Confirmed"],
  ["ðŸ“„", "Report/document"],
  ["ðŸ•’", "Time/please wait"],
  ["ðŸ“", "Location"],
  ["ðŸ“ž", "Call"],
];

const attachmentTypes = [
  ["Report PDF", "Lab_Report.pdf", "PDF Â· secure report"],
  ["Invoice PDF", "Invoice.pdf", "PDF Â· billing"],
  ["Prescription Image", "Prescription.jpg", "Image Â· prescription"],
  ["Receipt", "Payment_Receipt.pdf", "PDF Â· receipt"],
];

const drawerForms = {
  Link: [],
  Create: [],
  "Add Note": ["Internal Note"],
  "Add Tag": ["Tag Name"],
  Reassign: ["New Owner", "Reason"],
};

const linkForms = {
  Patient: ["Labmate Patient ID", "Mobile Number", "Patient Name"],
  Ticket: ["Ticket ID", "Reason"],
  Lead: ["Lead ID", "Reason"],
};

const createForms = {
  Ticket: ["Ticket Type", "Commitment Time", "Additional Information"],
  Lead: ["Name", "Mobile Number", "Follow-up Due"],
  "Home Collection": ["Preferred Date", "Address Area", "Slot"],
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"]/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
  }[char]));
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const json = await response.json();
  if (!response.ok || json.ok === false) throw new Error(json.error || "Request failed");
  return json;
}

function showToast(text) {
  els.toast.textContent = text;
  els.toast.classList.remove("hidden");
  window.setTimeout(() => els.toast.classList.add("hidden"), 2200);
}

function applyWorkflowState(stateRow) {
  if (!stateRow?.mobile) return null;
  state.allRows = state.allRows.map((row) => (
    row.mobile === stateRow.mobile
      ? {
        ...row,
        owner_user_id: stateRow.owner_user_id,
        owner_name: stateRow.owner_name,
        conversation_type: stateRow.conversation_type,
        workflow_status: stateRow.status,
        closed_at: stateRow.closed_at,
        closure_note: stateRow.closure_note,
      }
      : row
  ));
  return state.allRows.find((row) => row.mobile === stateRow.mobile);
}

function setComposerEnabled(enabled, placeholder) {
  els.replyText.disabled = !enabled;
  els.sendBtn.disabled = !enabled;
  [els.emojiBtn, els.attachBtn, els.dictBtn].forEach((button) => {
    if (button) button.disabled = !enabled;
  });
  els.replyText.placeholder = placeholder;
  if (!enabled) {
    els.replyText.value = "";
    state.selectedFile = null;
    if (els.fileInput) els.fileInput.value = "";
    renderAttachmentDraft();
    closeAssist();
  }
}

function displayTime(row) {
  return row.wabadatetime || String(row.datetimess || "").replace("T", " ").slice(0, 16);
}

function rowDate(row) {
  const raw = String(row.datetimess || row.wabadatetime || row.time || "").trim();
  if (!raw) return new Date();
  const isoDate = new Date(raw);
  if (!Number.isNaN(isoDate.getTime())) return isoDate;
  const match = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})(?:,\s*(\d{1,2}):(\d{2})\s*([AP]M))?/i);
  if (!match) return new Date();
  let hour = Number(match[4] || 0);
  const minute = Number(match[5] || 0);
  const meridiem = String(match[6] || "").toUpperCase();
  if (meridiem === "PM" && hour < 12) hour += 12;
  if (meridiem === "AM" && hour === 12) hour = 0;
  return new Date(Number(match[3]), Number(match[2]) - 1, Number(match[1]), hour, minute);
}

function dateKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function dateDividerLabel(row) {
  const date = rowDate(row);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (dateKey(date) === dateKey(today)) return "Today";
  if (dateKey(date) === dateKey(yesterday)) return "Yesterday";
  return date.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

function mediaUrl(value) {
  const text = String(value || "").trim();
  return text.startsWith("http://") || text.startsWith("https://") || text.startsWith("/uploads/") ? text : "";
}

function mediaInfo(row) {
  const imageUrl = mediaUrl(row.imgid) || mediaUrl(row.img);
  if (imageUrl || row.img) {
    return {
      kind: "image",
      label: row.msg || row.img || "Image attachment",
      url: imageUrl,
      id: row.imgid || row.img || "",
    };
  }
  const documentUrl = mediaUrl(row.docid);
  if (documentUrl || row.pdff || row.docid) {
    return {
      kind: "document",
      label: row.pdff || row.msg || "Document attachment",
      url: documentUrl,
      id: row.docid || "",
    };
  }
  return null;
}

function renderMedia(row) {
  const media = mediaInfo(row);
  if (!media) return "";
  const label = escapeHtml(media.label);
  const url = escapeHtml(media.url);
  const idText = media.id && !media.url ? `<span>${escapeHtml(media.id)}</span>` : "";
  if (media.kind === "image" && media.url) {
    return `
      <a class="imageBubble" href="${url}" target="_blank" rel="noreferrer" aria-label="${label}">
        <img src="${url}" alt="${label}" loading="lazy" />
      </a>
    `;
  }
  const href = media.url ? ` href="${url}" target="_blank" rel="noreferrer"` : "";
  return `
    <a class="fileBubble"${href}>
      <div><strong>${label}</strong><span>${media.kind === "document" ? "PDF / document" : "Image"}${media.url ? " - open" : " - media id"}</span>${idText}</div>
    </a>
  `;
}

function deliveryTick(row) {
  if (row.color !== "green") return "";
  const status = String(row.delivery_status || (row.provider_message_id ? "accepted" : "local")).toLowerCase();
  const title = status || "local";
  if (status.includes("fail") || status.includes("error") || status.includes("reject")) {
    return `<span class="deliveryTick failed" title="${escapeHtml(title)}">!</span>`;
  }
  if (status.includes("read")) {
    return `<span class="deliveryTick read" title="${escapeHtml(title)}">✓✓</span>`;
  }
  if (status.includes("deliver")) {
    return `<span class="deliveryTick delivered" title="${escapeHtml(title)}">✓✓</span>`;
  }
  if (status === "local") {
    return `<span class="deliveryTick local" title="${escapeHtml(title)}">✓</span>`;
  }
  return `<span class="deliveryTick accepted" title="${escapeHtml(title)}">✓✓</span>`;
}

function conversationType(row) {
  if (row.conversation_type) return row.conversation_type;
  const text = `${row.msg || ""} ${row.pdff || ""}`.toLowerCase();
  if (text.includes("invoice") || text.includes("bill")) return "Invoice";
  if (text.includes("home") || text.includes("collection") || text.includes("pickup")) return "Home Collection";
  if (text.includes("doctor") || text.includes("clinic")) return "Doctor";
  if (text.includes("lead") || text.includes("price") || text.includes("package")) return "Lead";
  return "Report";
}

function sla(row) {
  if (row.color === "green") return { value: 0, label: "0m", tone: "green" };
  const date = new Date(row.datetimess || Date.now());
  const value = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));
  const tone = value < 5 ? "green" : value <= 15 ? "amber" : value <= 30 ? "red" : "breach";
  return { value, label: `${value}m`, tone };
}

function ownerFor(row) {
  return row.owner_name || null;
}

function isClosed(row) {
  return row.workflow_status === "closed";
}

function tagClass(label) {
  return `tag tag-${label.toLowerCase().replaceAll(" ", "-")}`;
}

function mergeTags(row) {
  const type = conversationType(row);
  return Array.from(new Set([type].filter(Boolean)));
}

function conversationPreview(row) {
  const text = row.msg || row.pdff || row.img || "Attachment";
  return row.color === "green" ? `You: ${text}` : text;
}

function displayContactName(row) {
  return row.patient_name || row.empname || row.mobile;
}

function formatShortDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (!Number.isNaN(date.getTime())) {
    return date.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
  }
  return String(value).slice(0, 11);
}

function miniRecordHtml(id, name, date) {
  return `
    <article class="miniRecord">
      <strong>${escapeHtml(id || "-")}</strong>
      <span>${escapeHtml(name || "-")}</span>
      <time>${escapeHtml(formatShortDate(date))}</time>
    </article>
  `;
}

function renderMiniList(element, rows, mapRow, emptyText) {
  if (!element) return;
  const visible = (rows || []).slice(0, 4);
  if (!visible.length) {
    element.innerHTML = `<p class="emptyLink">${escapeHtml(emptyText)}</p>`;
    return;
  }
  element.innerHTML = visible.map((row) => {
    const mapped = mapRow(row);
    return miniRecordHtml(mapped.id, mapped.name, mapped.date);
  }).join("");
}

function setContextLoading() {
  if (els.leadList) els.leadList.innerHTML = '<p class="emptyLink">Loading leads...</p>';
  if (els.ticketList) els.ticketList.innerHTML = '<p class="emptyLink">Loading tickets...</p>';
  if (els.homeCollectionList) els.homeCollectionList.innerHTML = '<p class="emptyLink">Loading bookings...</p>';
}

function renderUnifiedLookup(data, row) {
  const caller = data?.caller;
  const linkedPatients = data?.linked_patients || [];
  const fallbackName = caller?.full_name || displayContactName(row);
  const fallbackNumber = caller?.primary_mobile || caller?.alternate_mobile || row.mobile;
  els.contactName.textContent = linkedPatients.length
    ? `${linkedPatients.length} linked patient${linkedPatients.length > 1 ? "s" : ""}`
    : fallbackName || "No linked contact";
  els.contactContext.innerHTML = linkedPatients.length
    ? linkedPatients.slice(0, 4).map((patient) => `
      <div>
        <dt>${escapeHtml(patient.full_name || "-")}</dt>
        <dd>${escapeHtml(patient.contact_mobile || patient.alternate_mobile || "-")}</dd>
      </div>
    `).join("")
    : `
      <div><dt>Name</dt><dd>${escapeHtml(fallbackName || "-")}</dd></div>
      <div><dt>Number</dt><dd>${escapeHtml(fallbackNumber || "-")}</dd></div>
    `;
  renderMiniList(
    els.homeCollectionList,
    data?.home_collection_bookings,
    (booking) => ({
      id: booking.booking_code || booking.id,
      name: booking.patients?.[0]?.full_name || caller?.full_name || "-",
      date: booking.preferred_visit_date || booking.created_at,
    }),
    "No home collection found."
  );
  renderMiniList(
    els.leadList,
    data?.leads,
    (lead) => ({ id: lead.lead_id || lead.id, name: lead.name, date: lead.created_at }),
    "No lead found."
  );
  renderMiniList(
    els.ticketList,
    data?.tickets,
    (ticket) => ({ id: ticket.id, name: ticket.patient_name || ticket.client_name, date: ticket.created_at || ticket.commitment_at }),
    "No ticket found."
  );
}

function visibleRows() {
  const q = els.searchInput.value.trim().toLowerCase();
  return state.allRows.filter((row) => {
    const owner = ownerFor(row);
    const currentSla = sla(row);
    const matchesQueue =
      state.activeQueue === "All Chats" ||
      (state.activeQueue === "Unassigned" && !owner) ||
      (state.activeQueue === "My Chats" && owner === currentUser) ||
      (state.activeQueue === "Team Chats" && owner && owner !== currentUser) ||
      (state.activeQueue === "Waiting For Patient" && row.color === "red") ||
      (state.activeQueue === "SLA Breached" && currentSla.value > 30) ||
      (state.activeQueue === "Archived" && false);
    const text = `${row.mobile} ${row.msg || ""} ${row.empname || ""} ${row.patient_name || ""} ${row.patient_code || ""} ${row.id}`.toLowerCase();
    return matchesQueue && (!q || text.includes(q));
  });
}

function updateQueueCounts() {
  const counts = {
    "All Chats": state.allRows.length,
    Unassigned: state.allRows.filter((row) => !ownerFor(row)).length,
    "My Chats": state.allRows.filter((row) => ownerFor(row) === currentUser).length,
    "Team Chats": state.allRows.filter((row) => {
      const owner = ownerFor(row);
      return owner && owner !== currentUser;
    }).length,
    "Waiting For Patient": state.allRows.filter((row) => row.color === "red").length,
    "SLA Breached": state.allRows.filter((row) => sla(row).value > 30).length,
    Archived: 0,
  };
  if (els.breachCount) els.breachCount.textContent = counts["SLA Breached"];
  els.queueNav.querySelectorAll("[data-queue]").forEach((button) => {
    button.querySelector("strong").textContent = counts[button.dataset.queue] ?? 0;
  });
}

function renderConversations() {
  state.rows = visibleRows();
  updateQueueCounts();
  if (!state.rows.length) {
    els.conversationList.innerHTML = '<p class="emptyLink">No patient conversations found.</p>';
    return;
  }
  els.conversationList.innerHTML = state.rows.map((row) => {
    const currentSla = sla(row);
    const owner = ownerFor(row);
    const selected = row.mobile === state.activeMobile ? " selected" : "";
    return `
      <button class="chatRow${selected}" type="button" data-mobile="${escapeHtml(row.mobile)}">
        <div class="rowTop">
          <strong>${escapeHtml(displayContactName(row))}</strong>
          <span>${escapeHtml(displayTime(row))}</span>
        </div>
        <p>${escapeHtml(conversationPreview(row))}</p>
        <div class="rowMeta">
          <span class="sla ${currentSla.tone}">${escapeHtml(currentSla.label)}</span>
          <span>${escapeHtml(owner || "Unassigned")}</span>
          ${isClosed(row) ? '<span class="status closed">Closed</span>' : ""}
          ${row.color === "red" ? "<b>1</b>" : ""}
        </div>
        <div class="tagList">
          ${mergeTags(row).map((tag) => `<span class="${tagClass(tag)}">${escapeHtml(tag)}</span>`).join("")}
        </div>
      </button>
    `;
  }).join("");
}

function renderMessages(rows) {
  if (!state.activeMobile) {
    els.messages.innerHTML = '<p class="emptyLink">Select a patient conversation to view messages.</p>';
    return;
  }
  if (!rows.length) {
    els.messages.innerHTML = '<p class="emptyLink">No messages in this conversation.</p>';
    return;
  }
  let activeDate = "";
  els.messages.innerHTML = rows.map((row) => {
    const nextDate = dateKey(rowDate(row));
    const divider = nextDate === activeDate ? "" : `<span class="dateDivider">${escapeHtml(dateDividerLabel(row))}</span>`;
    activeDate = nextDate;
    if (row.note) {
      return `${divider}<div class="internalNote">Note ${escapeHtml(row.note)} <span>${escapeHtml(row.time || "Now")}</span></div>`;
    }
    const media = mediaInfo(row);
    if (media) {
      return `${divider}
        <div class="bubble ${row.color === "green" ? "agent" : "customer"}">
          ${renderMedia(row)}
          ${row.msg ? `<p>${escapeHtml(row.msg)}</p>` : ""}
          <span class="messageMeta">${escapeHtml(displayTime(row))} ${deliveryTick(row)}</span>
        </div>
      `;
    }
    return `${divider}
      <div class="bubble ${row.color === "green" ? "agent" : "customer"}">
        <p>${escapeHtml(row.msg || "")}</p>
        <span class="messageMeta">${escapeHtml(displayTime(row))} ${deliveryTick(row)}</span>
      </div>
    `;
  }).join("");
  els.messages.scrollTop = els.messages.scrollHeight;
}

function updateSelected(row) {
  if (!row) return;
  const owner = ownerFor(row);
  const owned = Boolean(owner);
  const closed = isClosed(row);
  const ownedByCurrentUser = canCurrentUserAct(row);
  const type = conversationType(row);
  const currentSla = sla(row);
  els.activeMobile.textContent = displayContactName(row);
  els.activeSummary.textContent = `${row.mobile} Â· WhatsApp Official API`;
  els.ownerLine.innerHTML = `
    <span class="status ${owned ? "owned" : "unassigned"}">${owned ? "Owned" : "Unassigned"}</span>
    ${closed ? '<span class="status closed">Closed</span>' : ""}
    <span>Owner: ${escapeHtml(owner || "None")}</span>
    <span>Last reply: ${row.color === "green" ? escapeHtml(displayTime(row)) : "-"}</span>
  `;
  els.slaStatus.innerHTML = `<span class="sla ${currentSla.tone}">${escapeHtml(currentSla.label)}</span>`;
  els.takenAt.textContent = owned ? "Current session" : "Not taken";
  els.typeSelect.value = type;
  els.saveTypeBtn.className = "saveTypeBtn saved";
  els.saveTypeBtn.textContent = "Saved";
  els.typeSelect.disabled = !ownedByCurrentUser;
  els.saveTypeBtn.disabled = !ownedByCurrentUser;
  els.actionButtons.forEach((button) => {
    button.disabled = !ownedByCurrentUser;
    button.title = ownedByCurrentUser ? "" : owned ? `Assigned to ${owner}` : "Take ownership first";
  });
  els.takeBtn.disabled = owned || closed;
  els.takeBtn.textContent = owned
    ? ownedByCurrentUser ? "Ownership Locked" : `Assigned to ${owner}`
    : "Take Ownership";
  els.closeBtn.disabled = !ownedByCurrentUser || closed;
  els.closeBtn.textContent = closed ? "Closed" : "Close Conversation";
  setComposerEnabled(
    ownedByCurrentUser && !closed,
    closed
      ? "Conversation is closed"
      : ownedByCurrentUser
        ? "Type a WhatsApp reply..."
        : owned
          ? `Assigned to ${owner}`
          : "Take ownership to reply..."
  );
  els.tagStrip.innerHTML = mergeTags(row).map((tag) => `<span class="${tagClass(tag)}">${escapeHtml(tag)}</span>`).join("");
  els.tagNote.textContent = closed ? `Closed as ${type}` : `Current type: ${type}`;
  els.contactName.textContent = displayContactName(row);
  els.contactContext.innerHTML = `
    <div><dt>Name</dt><dd>${escapeHtml(displayContactName(row))}</dd></div>
    <div><dt>Number</dt><dd>${escapeHtml(row.mobile)}</dd></div>
  `;
  setContextLoading();
  els.auditSummary.textContent = `Owner: ${owner || "not assigned yet"}. Type: ${type}. Status: ${row.workflow_status || "open"}. Delivery: ${row.delivery_status || "not available"}. Row #${row.id}.`;
  if (els.topStateChip) els.topStateChip.textContent = `owner=${owned ? 1 : 0} links=1`;
}

async function loadConversations() {
  const params = new URLSearchParams();
  const query = els.searchInput.value.trim();
  if (query) params.set("q", query);
  if (els.dateInput?.value) params.set("date", els.dateInput.value);
  const data = await fetchJson(`/api/conversations?${params.toString()}`);
  state.allRows = data.rows || [];
  renderConversations();
  const selected = state.allRows.find((row) => row.mobile === state.activeMobile);
  if (selected) updateSelected(selected);
}

async function loadMessages(mobile) {
  state.activeMobile = mobile;
  const selected = state.allRows.find((row) => row.mobile === mobile);
  updateSelected(selected);
  renderConversations();
  const [messagesData, lookupData] = await Promise.all([
    fetchJson(`/api/conversations/${encodeURIComponent(mobile)}/messages`),
    fetchJson(`/api/mobile-lookup?mobile=${encodeURIComponent(mobile)}`),
  ]);
  renderMessages(messagesData.rows || []);
  renderUnifiedLookup(lookupData, selected || { mobile });
}

function setLayoutClasses() {
  els.hubGrid.classList.toggle("queuesHidden", !state.showQueues);
  els.hubGrid.classList.toggle("listHidden", !state.showChatList);
  document.querySelector(".queueSidebar").style.display = state.showQueues ? "" : "none";
  document.querySelector(".conversationList").style.display = state.showChatList ? "" : "none";
  els.toggleQueues.classList.toggle("active", state.showQueues);
  els.toggleChatList.classList.toggle("active", state.showChatList);
  els.toggleQueues.textContent = state.showQueues ? "Hide Queues" : "Show Queues";
  els.toggleChatList.textContent = state.showChatList ? "Hide Chat List" : "Show Chat List";
}

function openAssist(type) {
  document.querySelectorAll(".composerTool").forEach((button) => button.classList.remove("active"));
  const source = type === "emoji" ? professionalEmojis : type === "attach" ? attachmentTypes : replyDictionary;
  const panelClass = type === "emoji" ? "emojiPanel" : type === "attach" ? "attachmentPanel" : "dictionaryPanel";
  const title = type === "emoji" ? "Professional emojis" : type === "attach" ? "Attach work file" : "Local dictionary";
  els.assistPanel.className = `assistPanel ${panelClass}`;
  els.assistPanel.innerHTML = `
    <strong>${title}</strong>
    <div class="${type === "dict" ? "dictionaryChips" : ""}">
      ${source.map(([value, hint, meta]) => `
        <button type="button" data-assist="${type}" data-value="${escapeHtml(type === "attach" ? hint : value)}">
          <strong>${escapeHtml(value)}</strong>
          ${hint ? `<span>${escapeHtml(meta || hint)}</span>` : ""}
        </button>
      `).join("")}
    </div>
  `;
}

function closeAssist() {
  els.assistPanel.className = "assistPanel hidden";
}

function renderAttachmentDraft() {
  document.querySelector(".attachmentDraft")?.remove();
  if (!state.selectedFile) return;
  const draft = document.createElement("div");
  draft.className = "attachmentDraft";
  draft.innerHTML = `
    <span>${escapeHtml(state.selectedFile.name)}</span>
    <button type="button" id="clearAttachment">Remove</button>
  `;
  els.replyForm.insertAdjacentElement("afterend", draft);
  document.querySelector("#clearAttachment").addEventListener("click", () => {
    state.selectedFile = null;
    if (els.fileInput) els.fileInput.value = "";
    renderAttachmentDraft();
  });
}

async function uploadSelectedFile() {
  if (!state.selectedFile) return null;
  const formData = new FormData();
  formData.append("file", state.selectedFile);
  const data = await fetchJson("/api/uploads", {
    method: "POST",
    body: formData,
  });
  return data.media;
}

function drawerFieldsHtml(fields) {
  return fields.map((field) => `
    <label class="modalField">
      ${escapeHtml(field)}
      ${field === "New Owner"
        ? '<input class="ownerSearch" list="ownerOptions" data-field="New Owner" autocomplete="off" placeholder="Search owner name" /><datalist id="ownerOptions"></datalist><input type="hidden" data-field="New Owner ID" />'
        : field.includes("Information") || field.includes("Note")
          ? `<textarea data-field="${escapeHtml(field)}"></textarea>`
          : `<input data-field="${escapeHtml(field)}" />`}
    </label>
  `).join("");
}

function fieldValue(label) {
  return els.drawerFields.querySelector(`[data-field="${CSS.escape(label)}"]`)?.value?.trim() || "";
}

async function loadUsers(query = "") {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  const data = await fetchJson(`/api/users?${params.toString()}`);
  state.userOptions = data.users || [];
  const options = document.querySelector("#ownerOptions");
  if (options) {
    options.innerHTML = state.userOptions.map((user) => (
      `<option value="${escapeHtml(user.display_name)}" data-id="${user.id}">${escapeHtml(user.username)}</option>`
    )).join("");
  }
}

function selectedOwnerId() {
  const name = fieldValue("New Owner").toLowerCase();
  const match = state.userOptions.find((user) => (
    user.display_name.toLowerCase() === name || user.username.toLowerCase() === name
  ));
  return match?.id || "";
}

function canCurrentUserAct(row) {
  return Boolean(row && Number(row.owner_user_id || 0) === currentUserId && !isClosed(row));
}

function openDrawer(title) {
  const selected = state.allRows.find((row) => row.mobile === state.activeMobile);
  if (!canCurrentUserAct(selected)) {
    showToast(ownerFor(selected) ? `Assigned to ${ownerFor(selected)}` : "Take ownership first");
    return;
  }
  state.drawerMode = title;
  els.drawerTitle.textContent = title;
  let question = "";
  let fields = drawerForms[title] || [];
  if (title === "Create") {
    question = `
      <section class="createQuestion">
        <h3>What do you want to create?</h3>
        <div>${Object.keys(createForms).map((type, index) => `<button class="${index === 0 ? "active" : ""}" type="button" data-create-type="${type}">${type}</button>`).join("")}</div>
      </section>
    `;
    fields = createForms.Ticket;
  }
  if (title === "Link") {
    question = `
      <section class="createQuestion">
        <h3>What do you want to link?</h3>
        <div>${Object.keys(linkForms).map((type, index) => `<button class="${index === 0 ? "active" : ""}" type="button" data-link-type="${type}">${type}</button>`).join("")}</div>
      </section>
    `;
    fields = linkForms.Patient;
  }
  if (title === "Close Conversation") {
    question = `
      <section class="closureQuestion">
        <h3>Mark type before closure</h3>
        <p>CCE must classify the conversation so tags like Invoice, Report, and Lead have a clear source.</p>
        <label class="modalField">Conversation Type
          <select id="closureType"><option value="">Select type</option>${closureTypes.map((type) => `<option>${type}</option>`).join("")}</select>
        </label>
      </section>
    `;
    fields = ["Closure Note"];
  }
  els.drawerQuestion.innerHTML = question;
  els.drawerFields.innerHTML = drawerFieldsHtml(fields);
  els.drawerSave.textContent = title === "Close Conversation" ? "Close Conversation" : "Save";
  els.drawerBackdrop.classList.remove("hidden");
  if (title === "Reassign") loadUsers().catch((error) => showToast(error.message));
}

els.queueNav.addEventListener("click", (event) => {
  const button = event.target.closest("[data-queue]");
  if (!button) return;
  state.activeQueue = button.dataset.queue;
  els.activeQueueLabel.textContent = state.activeQueue;
  els.queueNav.querySelectorAll("[data-queue]").forEach((item) => item.classList.toggle("active", item === button));
  renderConversations();
});

els.conversationList.addEventListener("click", (event) => {
  const button = event.target.closest("[data-mobile]");
  if (!button) return;
  loadMessages(button.dataset.mobile).catch((error) => showToast(error.message));
});

els.searchInput.addEventListener("input", () => {
  clearTimeout(state.searchTimer);
  state.searchTimer = setTimeout(() => loadConversations().catch((error) => showToast(error.message)), 250);
});

els.dateInput?.addEventListener("change", () => loadConversations().catch((error) => showToast(error.message)));

els.toggleQueues.addEventListener("click", () => {
  state.showQueues = !state.showQueues;
  setLayoutClasses();
});

els.toggleChatList.addEventListener("click", () => {
  state.showChatList = !state.showChatList;
  setLayoutClasses();
});

els.takeBtn.addEventListener("click", async () => {
  if (!state.activeMobile) return;
  try {
    const data = await fetchJson(`/api/conversations/${encodeURIComponent(state.activeMobile)}/ownership`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const selected = applyWorkflowState(data.state);
    updateSelected(selected);
    renderConversations();
    showToast(`Ownership locked to ${currentUser}`);
  } catch (error) {
    showToast(error.message);
  }
});

els.closeBtn.addEventListener("click", () => {
  if (state.activeMobile) openDrawer("Close Conversation");
});

els.typeSelect.addEventListener("change", () => {
  const selected = state.allRows.find((row) => row.mobile === state.activeMobile);
  if (!canCurrentUserAct(selected)) return;
  els.saveTypeBtn.className = "saveTypeBtn update";
  els.saveTypeBtn.textContent = "Update Type";
});

els.saveTypeBtn.addEventListener("click", async () => {
  if (!state.activeMobile) return;
  const current = state.allRows.find((row) => row.mobile === state.activeMobile);
  if (!canCurrentUserAct(current)) {
    showToast(ownerFor(current) ? `Assigned to ${ownerFor(current)}` : "Take ownership first");
    return;
  }
  try {
    const data = await fetchJson(`/api/conversations/${encodeURIComponent(state.activeMobile)}/type`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_type: els.typeSelect.value }),
    });
    const selected = applyWorkflowState(data.state);
    updateSelected(selected);
    renderConversations();
    showToast(`Conversation type saved as ${els.typeSelect.value}`);
  } catch (error) {
    showToast(error.message);
  }
});

els.replyForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const msg = els.replyText.value.trim();
  const selected = state.allRows.find((row) => row.mobile === state.activeMobile);
  const canReply = canCurrentUserAct(selected);
  if (!canReply) {
    showToast("Take ownership before replying");
    setComposerEnabled(false, "Take ownership to reply...");
    return;
  }
  if (!state.activeMobile || (!msg && !state.selectedFile)) return;
  els.sendBtn.disabled = true;
  try {
    const media = await uploadSelectedFile();
    await fetchJson(`/api/conversations/${encodeURIComponent(state.activeMobile)}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ msg, empname: currentUser, media }),
    });
    els.replyText.value = "";
    state.selectedFile = null;
    if (els.fileInput) els.fileInput.value = "";
    renderAttachmentDraft();
    closeAssist();
    await loadConversations();
    await loadMessages(state.activeMobile);
    showToast(media ? "Attachment sent through WhatsApp Official API" : "Message sent through WhatsApp Official API");
  } catch (error) {
    showToast(error.message);
  } finally {
    const current = state.allRows.find((row) => row.mobile === state.activeMobile);
    els.sendBtn.disabled = !canCurrentUserAct(current);
  }
});

document.querySelector("#emojiBtn").addEventListener("click", () => openAssist("emoji"));
document.querySelector("#dictBtn").addEventListener("click", () => openAssist("dict"));
document.querySelector("#attachBtn").addEventListener("click", () => {
  closeAssist();
  els.fileInput?.click();
});

els.fileInput?.addEventListener("change", () => {
  const file = els.fileInput.files?.[0];
  if (!file) return;
  const allowed = ["image/jpeg", "image/png", "image/webp", "application/pdf"];
  if (!allowed.includes(file.type)) {
    showToast("Only JPG, PNG, WEBP, and PDF files are allowed");
    els.fileInput.value = "";
    return;
  }
  state.selectedFile = file;
  renderAttachmentDraft();
});

els.assistPanel.addEventListener("click", (event) => {
  const button = event.target.closest("[data-value]");
  if (!button) return;
  const value = button.dataset.value;
  els.replyText.value = `${els.replyText.value}${els.replyText.value ? " " : ""}${value} `;
  closeAssist();
  els.replyText.focus();
});

document.querySelectorAll("[data-drawer]").forEach((button) => {
  button.addEventListener("click", () => openDrawer(button.dataset.drawer));
});

els.drawerQuestion.addEventListener("click", (event) => {
  const createButton = event.target.closest("[data-create-type]");
  const linkButton = event.target.closest("[data-link-type]");
  if (createButton) {
    els.drawerQuestion.querySelectorAll("[data-create-type]").forEach((button) => button.classList.toggle("active", button === createButton));
    els.drawerFields.innerHTML = drawerFieldsHtml(createForms[createButton.dataset.createType]);
  }
  if (linkButton) {
    els.drawerQuestion.querySelectorAll("[data-link-type]").forEach((button) => button.classList.toggle("active", button === linkButton));
    els.drawerFields.innerHTML = drawerFieldsHtml(linkForms[linkButton.dataset.linkType]);
  }
});

els.drawerFields.addEventListener("input", (event) => {
  const input = event.target.closest(".ownerSearch");
  if (!input) return;
  clearTimeout(state.searchTimer);
  state.searchTimer = setTimeout(() => loadUsers(input.value).catch((error) => showToast(error.message)), 200);
});

[els.drawerClose, els.drawerCancel].forEach((button) => {
  button.addEventListener("click", () => els.drawerBackdrop.classList.add("hidden"));
});

els.drawerSave.addEventListener("click", async () => {
  if (!state.activeMobile) return;
  try {
  if (state.drawerMode === "Close Conversation") {
    const closureType = document.querySelector("#closureType")?.value || els.typeSelect.value;
    if (!closureType) {
      showToast("Select conversation type before closure");
      return;
    }
    const data = await fetchJson(`/api/conversations/${encodeURIComponent(state.activeMobile)}/close`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_type: closureType, note: fieldValue("Closure Note") }),
    });
    const selected = applyWorkflowState(data.state);
    updateSelected(selected);
    renderConversations();
    showToast(`Conversation closed as ${closureType}`);
  } else if (state.drawerMode === "Add Note") {
    const note = fieldValue("Internal Note");
    if (!note) {
      showToast("Add note text first");
      return;
    }
    await fetchJson(`/api/conversations/${encodeURIComponent(state.activeMobile)}/notes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note }),
    });
    await loadMessages(state.activeMobile);
    showToast("Note saved to conversation");
  } else if (state.drawerMode === "Reassign") {
    const ownerUserId = selectedOwnerId();
    if (!ownerUserId) {
      showToast("Select a valid owner");
      return;
    }
    const data = await fetchJson(`/api/conversations/${encodeURIComponent(state.activeMobile)}/reassign`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ owner_user_id: ownerUserId, reason: fieldValue("Reason") }),
    });
    const selected = applyWorkflowState(data.state);
    updateSelected(selected);
    renderConversations();
    showToast(`Conversation reassigned to ${ownerFor(selected)}`);
  } else {
    showToast(`${state.drawerMode} saved to conversation context`);
  }
  els.drawerBackdrop.classList.add("hidden");
  } catch (error) {
    showToast(error.message);
  }
});

if (els.dateInput) els.dateInput.valueAsDate = new Date();
setComposerEnabled(false, "Take ownership to reply...");
setLayoutClasses();
loadConversations().catch((error) => showToast(error.message));


