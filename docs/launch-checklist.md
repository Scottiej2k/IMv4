# Launch checklist

Everything needed between today and selling the course. `[x]` done, `[ ]` to do.
Decisions are dated; the details live in the linked docs.

## 1. Content

- [x] Book format, voices and narrator pace chosen (CLAUDE.md, config/voices.json).
- [x] S5E3's date fixed (Chicago answer due by February).
- [ ] Owner's review of S1E1–S1E5 and the S5E3 pilot.
- [ ] One B2 test chapter before B2 production (B2 is 75 of the 200 chapters).
- [ ] Production batches, S1E6 onward (`run_batch.py`, `--jobs 1` for tight continuity).
- [ ] Native Italian speaker spot-checks: 3–5 chapters now, then a few per season.
- [ ] Skim continuity entries after each batch (they can over-reach or come out in Italian).

## 2. Audio

- [x] Voice model: **Gemini 3.8 Flash TTS**, not Flash Lite (owner, 2026-09-28).
- [x] Gemini TTS licensing checked: fine for commercial use (owner, 2026-09-28).
- [x] Storage in Cloudflare R2 (`scripts/storage.py`). S1E1 and S1E2 stored.
- [x] Each chapter opens with the English introduction (S1E2 done).
- [ ] S1E1: add the English introduction (its clips were lost; prepend just the intro clip).
- [ ] Owner's listening check of S1E1/S1E2 audio and read-along.
- [ ] Audio for every chapter, in batches, reviewed in the reader. Cost is about $1.50 per chapter,
      roughly $250–350 for the course: top up the OpenRouter balance ahead of time.
- [ ] Decide whether estimated word timings are good enough or forced alignment is needed
      (docs/read-along.md). Can be added later without remaking audio.
- [ ] Optional: back up compressed clips to R2 so later text fixes only re-make changed lines.
- [ ] DeepSeek (text) terms: confirm commercial use of its output.
- [ ] A short "voices are AI-generated" note on the site.

## 3. The app (Replit)

Plan: code in GitHub, Replit pulls and runs it (docs/app-spec.md).

- [x] Accounts and payment decided (owner, 2026-09-28): Clerk (email + Google); Stripe subscription,
      monthly or yearly, no trial, access until the end of the paid period; free = first episode of
      each level (S1E1, S2E1, S4E1, S6E1). docs/app-spec.md §5.
- [x] Privacy policy and contact pages drafted: `app/privacy.html`, `app/contact.html`, with the
      contact form's server code in `app/server/contact.js`.
- [x] Database schema: `app/server/schema.sql` (PostgreSQL; tested: time caps, access check,
      account deletion). Run it once on Replit's database.
- [ ] Build the app: server, database, Clerk sign-in, Stripe Checkout + Customer Portal + webhooks,
      server-side locking, signed R2 audio links, contact route.
- [ ] Test end to end on Replit in Stripe test mode: subscribe, switch plan, cancel, failed renewal.
- [ ] Account deletion and data export (GDPR; also needed for app stores later).
- [ ] Error alerts and database backups.
- [ ] Privacy-friendly analytics: sign-ups, free → paid, how far people get (then list it in the
      privacy policy).
- [ ] Mobile and accessibility check.

## 4. Accounts and services to set up (owner)

- [ ] Domain name, connected to the Replit deployment.
- [ ] Replit paid deployment and its PostgreSQL database, not the key-value "Replit DB" (include in monthly costs).
- [ ] Clerk: account and app; for launch, your own Google sign-in credentials (Google Cloud) and
      the verified domain (Clerk's shared Google login is for testing only).
- [ ] Stripe: account, business and bank details, product "Full course" with a monthly and a
      yearly price, Customer Portal switched on, webhook pointed at the live app.
- [ ] Stripe Tax (or an accountant's advice) for sales tax and EU/UK VAT.
- [ ] Resend (or another email service) for the contact form: verify the domain, then Replit
      secrets `RESEND_API_KEY`, `CONTACT_TO`, `CONTACT_FROM`.
- [ ] A support email address on the domain (shown on the site and on Stripe receipts).
- [ ] R2: a CORS rule so the app's domain can play audio from the bucket (bucket stays private).

## 5. Legal and business

- [ ] Decide who sells: you personally or a company. Stripe needs the legal name and tax details.
- [ ] Privacy policy: fill the highlighted placeholders in `app/privacy.html` (name, address, date,
      email provider, analytics, retention, minimum age) and have it reviewed.
- [ ] Terms of Service (subscriptions, cancellation, acceptable use).
- [ ] Refund policy.
- [ ] Trademark search on "Input Masters".

## 6. Launch

- [ ] Beta: 5–10 learners on the free episodes; fix what confuses them.
- [ ] Switch Stripe to live keys; make one real purchase and refund it.
- [ ] Public launch.
