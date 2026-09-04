// founder-desk chat. One plate per answer; the plate's markings carry the
// authority tier and the freshness state, per DESIGN.md.

const TIER = { 1: "Act or Rules", 2: "Notification", 3: "Official guidance" };

const OPENERS = [
  "Do I need GST registration before my first sale?",
  "Can a one person company get Startup India benefits?",
  "Does an apprentice have to be enrolled in provident fund?",
  "Do I need shops and establishment registration?",
];

const thread = document.getElementById("thread");
const form = document.getElementById("ask-form");
const input = document.getElementById("ask");
const send = document.getElementById("send");
const known = document.getElementById("known");

const sessionId =
  (crypto.randomUUID && crypto.randomUUID()) || String(Date.now() + Math.random());

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function showOpening() {
  const wrap = el("div", "opening");
  wrap.append(
    el("h2", null, "Ask about your first year"),
    el(
      "p",
      null,
      "Every answer is quoted word for word from an official government source, " +
        "with the date it was fetched. When the sources cannot answer, this says so " +
        "instead of guessing.",
    ),
  );
  const list = el("ul");
  for (const q of OPENERS) {
    const li = el("li");
    const button = el("button", null, q);
    button.type = "button";
    button.addEventListener("click", () => {
      input.value = q;
      form.requestSubmit();
    });
    li.append(button);
    list.append(li);
  }
  wrap.append(list);
  thread.append(wrap);
}

function pendingPlate(question) {
  const turn = el("section", "turn");
  turn.append(el("h2", "turn__question", question));
  turn.dataset.typed = question;
  const plate = el("article", "plate plate--pending");
  const face = el("div", "plate__face");
  face.append(el("div", "skeleton"), el("div", "skeleton"), el("div", "skeleton"));
  plate.append(face);
  turn.append(plate);
  thread.append(turn);
  turn.scrollIntoView({ behavior: "smooth", block: "start" });
  return { turn, plate };
}

function citation(span) {
  const li = el("li", "cite");
  li.dataset.state = span.status;
  const link = el("a", null, span.citation);
  link.href = span.url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  const title = el("span", "cite__title");
  title.append(link);
  const fetched = new Date(span.fetched_at).toISOString().slice(0, 10);
  li.append(
    title,
    el("span", "cite__meta", `${span.publisher} · ${TIER[span.authority_tier]} · fetched ${fetched}`),
  );
  return li;
}

function renderPlate(plate, reply) {
  const answer = reply.answer;
  // When a short reply resolved the previous clarifying question, the heading
  // must show the question that was actually answered. Leaving "Maharashtra"
  // above a paragraph about contract labour reads as a non-sequitur.
  const turn = plate.closest(".turn");
  if (reply.resolved_from_pending && turn) {
    const heading = turn.querySelector(".turn__question");
    heading.textContent = answer.question;
    const note = el("p", "turn__resolved", `you answered: ${turn.dataset.typed}`);
    heading.after(note);
  }
  plate.className = "plate";
  plate.dataset.kind = answer.kind;

  const cited = answer.cited_spans || [];
  const worst = cited.find((s) => s.status !== "current");
  plate.dataset.state = worst ? worst.status : "current";
  // The reserved hue marks the plate you are reading now, and only that.
  for (const other of thread.querySelectorAll(".plate[data-active]")) {
    other.removeAttribute("data-active");
  }
  plate.dataset.active = "yes";

  const band = el("div", "plate__band");
  const lead = cited[0];
  band.dataset.tier = lead ? String(lead.authority_tier) : "";
  band.append(
    el("span", "plate__tier", lead ? TIER[lead.authority_tier] : labelFor(answer.kind)),
    el("span", "plate__publisher", lead ? lead.publisher : ""),
  );

  const face = el("div", "plate__face");
  if (answer.applies_to) {
    const a = answer.applies_to;
    const bits = [
      a.entity_type ? `entity: ${a.entity_type}` : "entity: unspecified",
      a.state ? `state: ${a.state}` : "state: all-India",
    ];
    face.append(el("p", "plate__applies", bits.join(" · ")));
  }

  const body = el("div", "plate__body");
  if (answer.kind === "grounded") {
    for (const claim of answer.claims) body.append(el("p", "quote", claim.text));
  } else if (answer.kind === "clarify") {
    body.append(el("p", "ask", answer.clarifying_question));
  } else if (answer.kind === "informational_only") {
    body.append(el("p", "ask", "This asks for a judgement no published source can make for you."));
    for (const c of answer.considerations) body.append(el("p", "factor", c));
  } else {
    body.append(
      el(
        "p",
        "ask",
        "I cannot ground an answer to this in the allowlisted sources, so I am not going to guess.",
      ),
    );
    const list = el("ul", "plate__searched");
    for (const s of answer.searched) list.append(el("li", null, s));
    body.append(list);
  }
  face.append(body);

  const cites = el("ul", "plate__cites");
  for (const span of cited) cites.append(citation(span));
  face.append(cites);

  for (const pos of ["tl", "tr", "bl", "br"]) {
    const rivet = el("i", `rivet rivet--${pos}`);
    rivet.setAttribute("aria-hidden", "true");
    face.append(rivet);
  }
  plate.replaceChildren(band, face);
}

function labelFor(kind) {
  if (kind === "refused") return "Not covered";
  if (kind === "clarify") return "Needs one more fact";
  if (kind === "informational_only") return "Not advice";
  return "Answer";
}

async function submit(question) {
  const { plate } = pendingPlate(question);
  input.value = "";
  input.disabled = true;
  send.disabled = true;

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message: question }),
    });
    if (!response.ok) throw new Error(`${response.status}`);
    const reply = await response.json();
    renderPlate(plate, reply);
    known.textContent = reply.known;
    known.dataset.established = reply.known.includes(":") ? "yes" : "no";
  } catch (error) {
    plate.className = "plate";
    plate.dataset.kind = "refused";
    plate.dataset.state = "current";
    const band = el("div", "plate__band");
    band.append(el("span", "plate__tier", "Service unavailable"));
    const face = el("div", "plate__face");
    face.append(
      el("div", "plate__body").appendChild(
        el(
          "p",
          "ask",
          "The service did not answer. Check that it is running, then ask again — " +
            "nothing was sent anywhere else.",
        ),
      ).parentElement,
    );
    plate.replaceChildren(band, face);
  } finally {
    input.disabled = false;
    send.disabled = false;
    input.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const question = input.value.trim();
  if (!question) return;
  const opening = thread.querySelector(".opening");
  if (opening) opening.remove();
  submit(question);
});

showOpening();
input.focus();
