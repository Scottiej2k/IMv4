// Contact form → email to the owner. Plug into the Replit app's server as POST /api/contact
// (e.g. Express: app.post("/api/contact", express.json({ limit: "20kb" }), contactRoute)).
// Sends through Resend's HTTP API (https://resend.com); no npm packages needed (Node 18+ has fetch).
//
// Replit Secrets:
//   RESEND_API_KEY  the Resend API key
//   CONTACT_TO      where messages go (the owner's inbox)
//   CONTACT_FROM    a sender on a domain verified in Resend, e.g. "Input Masters <contact@yourdomain.com>"

const TOPICS = new Set(["Account and sign-in", "Subscription and billing", "The course content",
  "Privacy and my data", "Something else"]);
const LIMIT = 5, WINDOW_MS = 60 * 60 * 1000;          // at most 5 messages per IP per hour
const recent = new Map();                              // ip -> [timestamps]; in memory, fine for one server

function tooMany(ip) {
  const now = Date.now();
  const times = (recent.get(ip) || []).filter((t) => now - t < WINDOW_MS);
  times.push(now);
  recent.set(ip, times);
  return times.length > LIMIT;
}

async function contactRoute(req, res) {
  const b = req.body || {};
  const name = String(b.name || "").trim().slice(0, 100);
  const email = String(b.email || "").trim().slice(0, 200);
  const message = String(b.message || "").trim().slice(0, 5000);
  const topic = TOPICS.has(b.topic) ? b.topic : "Something else";

  if (b.website) return res.json({ ok: true });       // spam trap filled: pretend it worked
  if (!name || !message || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || /[\r\n]/.test(email)) {
    return res.status(400).json({ ok: false, error: "Please fill in your name, a valid email and your message." });
  }
  if (tooMany(req.ip)) {
    return res.status(429).json({ ok: false, error: "Too many messages. Please try again later." });
  }

  const r = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${process.env.RESEND_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      from: process.env.CONTACT_FROM,
      to: [process.env.CONTACT_TO],
      reply_to: email,                                  // hitting Reply answers the learner directly
      subject: `[Input Masters] ${topic}: ${name.replace(/[\r\n]+/g, " ")}`,
      text: `From: ${name} <${email}>\nTopic: ${topic}\n\n${message}\n`,
    }),
  }).catch(() => null);

  if (!r || !r.ok) {
    console.error("contact: email failed", r && r.status, r && (await r.text().catch(() => "")));
    return res.status(502).json({ ok: false, error: "Sorry, your message couldn't be sent. Please try again in a few minutes." });
  }
  res.json({ ok: true });
}

module.exports = { contactRoute };
