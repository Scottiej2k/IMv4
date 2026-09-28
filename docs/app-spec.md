# Input Masters · Italian: learner app spec (hand-off for Replit)

The course content is made in this repo. The learner app is built on Replit once all 200 chapters
and their audio exist. The working prototype is `app/index.html`, published at
https://claude.ai/artifact/6nEntWJYwZ3BeFeHAGY3KN. It runs in the browser only. It is the
reference for screens and behaviour. The Replit app adds accounts, payment and server-side storage.

Names:
- **Product:** Input Masters · Italian.
- **Sitcom:** *Via dei Tigli*.
- **In the app, a chapter is also called an episode.**

## 1. Content bundle

`python3 scripts/export_app.py` writes `app/content/`. That folder is what the app imports. Re-run
it whenever chapters or audio change.

| File | What it holds |
|---|---|
| `catalog.json` | The course. Holds `title`, `series`, `free_chapters` (3), `levels` (vocab goal per level), `speakers` (id → name) and `locations` (id → name). Also holds `chapters`: every planned chapter in order. |
| `chapters/<id>.json` | One written chapter. Holds `id`, `n`, `level`, `title` {it, en}, `theme`, `grammar_name` and `intro`. Also holds `scenes`, `vocab`, `grammar` (Markdown), `anki` (CSV text), `timing` and `audio` (the path of the mp3). |
| `audio/<id>.mp3` | The chapter's audio: 32 kbit/s mono MP3, about 7 MB for a 28-minute A1 chapter. |

Each row in `catalog.chapters` has these fields:
- `id`, `n`, `level`, `season`, `episode`;
- `theme` (the chapter's heading);
- `title` {it, en} (the story's title);
- `grammar`;
- `free` (n ≤ 3);
- `written`;
- `vocab_through`: vocabulary items taught up to and including this chapter. For a chapter not yet written, the level's typical count stands in.

A written row also has `intro`, `words`, `segments`, `vocab` and `audio_minutes` (the last only
when its audio exists).

Chapter text:
- **`scenes[]`:** each scene has `location`, `time` and `paragraphs`. A paragraph is a list of segments (sentences).
- **Segment:** `{ id, it, en, tokens, speakers }`.
  - `it` and `en` use `**bold**` for focus words and `_italics_` for thoughts.
  - `tokens` is `[[text, word index or -1, flags]]`, where flags are `b` (bold) and `i` (italic). Word `k` of segment `s` has the id `s.k`.
- **`timing.words`:** `{ "<seg>.<k>": [start, end] }` in seconds.
- **`timing.segments`:** `{ "<seg>": [start, end] }`.
- These timings drive the read-along underline and "Play from here" (details in docs/read-along.md).

Size at 200 chapters: roughly 2 GB of audio (later chapters are longer) and about 50 MB of JSON. Serve both from object storage
or a CDN, not from the app server's disk.

## 2. Screens

**Landing** (for people who aren't signed in):
- the hero, with a sample page of the story;
- the method (comprehensible input), with figures and the comparison with phrase apps;
- the show (the street, the cast);
- what each episode includes;
- the path from A1 to B2;
- pricing (Free: episodes 1–3; Full course: all 200).

Its buttons are "Start for free" (sign up, then the library) and "Unlock all episodes" (Stripe
Checkout, see §5).

**Library** (home after sign-in):
1. **Pick up where you left off:** a clear, modest row showing the chapter, the tab they were on and the % read, with a Continue button. It reopens the last chapter on the last tab, at the last sentence read. For a new learner it says "Start Chapter 1".
2. **Summary:** four figures.
   - total reading time;
   - total listening time;
   - words met;
   - time this week.
3. **Chapters by level.** Each row shows:
   - the number, theme and Italian title;
   - "Free" or "Full course" (locked);
   - reading and listening time for that chapter;
   - a progress bar.

   Chapters not yet released show as "N more episodes in production".

**Chapter:**
- **Header:** level, number, theme, and "Grammar: …".
- **Tabs:** Vocabulary, Grammar, Story, Side by side. The tab bar sticks under the top bar and also carries the two timers (§3).
- **Story:** the story title, then "About this episode" (the intro), then the scenes as book paragraphs. Tapping a sentence gives "Play from here" and "Translation". An option shows English under every sentence.
- **Side by side:** the intro, then one row per sentence: speaker, Italian, English.
- **Vocabulary:**
  - "By the end of this episode you'll have met N words";
  - the list, each word with its sentence from the story and an "I know it" tick;
  - a "Download for Anki" button (CSV).
- **Grammar:** the lesson (Markdown).
- **Player bar** (Story and Side by side):
  - Play/Pause, "Resume where you left off", "Clear underlines";
  - speed 0.75–1.5×;
  - the position.
  - While audio plays, each word underlines as it's spoken and stays underlined. The text scrolls to follow.
- **Locked chapter:** shows the intro and an unlock button instead of the text.

## 3. Time tracking (the owner's rules)

- **Reading** counts while all of these hold:
  - a chapter is open;
  - the browser tab is in front;
  - the learner hasn't paused the reading timer (a Pause/Resume button on the timer);
  - there has been a click, tap, scroll (wheel or touch) or key press in the last 2 minutes.

  After 2 minutes without one, it pauses by itself and says so. The next click, tap or scroll restarts it.
- **Listening** counts while the chapter's audio is actually playing. Time is measured by the clock, so 1.5× speed still counts real minutes.
- **Both can run at once:** reading along while listening counts as both.
- **Where time is added:** to the chapter, to the course total and to the day (for "this week" and later streaks or charts).
- **Server side:** the app sends the time it has counted in small batches (e.g. every 15–30 s, and when the page is hidden or closed). The server adds each batch to the totals. It never replaces a total with one sent by the browser, and it caps any one batch at the time since the last one.

## 4. Progress to store per user

The prototype keeps it all in one object (the `Progress` module in `app/index.html`). On Replit
the same object moves to the database.

| Data | Shape |
|---|---|
| Account | id, email, created, `started` |
| Entitlement | `unlocked` (bool), Stripe customer id, purchase date |
| Last chapter | `last` (chapter id) |
| Per chapter | `read` s, `listen` s, `tab`, `at` (sentence id of the reading place), `far` (furthest sentence index reached, for %), `played` {segment id: last word index heard}, `t` (audio position, s) |
| Totals | `read` s, `listen` s |
| Per day | date → `read`, `listen` s |
| Known words | set of vocab item ids ticked "I know it" |
| Settings | playback `speed`, "English under every sentence" |

The fields work like this:
- **% read:** `far + 1` over the chapter's `segments` (from the catalog). A sentence counts once it has scrolled past the middle of the screen or has been heard.
- **Words met:** the `vocab_through` of the furthest chapter the learner has opened. Show it against the course goal (6,000, a high B2).

Suggested tables (PostgreSQL):
- `users`
- `entitlements`
- `chapter_progress` (user, chapter → the per-chapter fields)
- `daily_time` (user, date, read, listen)
- `known_words` (user, vocab id)

## 5. Free chapters and payment (Stripe)

- **Free:** chapters 1–3 (`catalog.free_chapters`), with every feature.
- **Unlocking:**
  1. "Unlock all episodes" starts a **Stripe Checkout** session for the full course. It is one price, set later (one-off or subscription).
  2. Stripe's **webhook** (`checkout.session.completed`) tells the server the payment went through.
  3. Only the server then sets `unlocked = true`. The browser never decides it.
- **Locking must happen on the server:** don't send a locked chapter's JSON or audio to a user who hasn't unlocked it. The catalog can list every chapter, but only the intro of a locked one. Serve locked files through the app (after checking the user) or through short-lived signed links. The prototype only hides them on screen, which isn't protection.
- **Prototype:** the prototype's "Simulate unlock" button is for testing and must not ship.

## 6. Not in the prototype yet (ideas for later)

- Accounts and sign-in, syncing across devices.
- Streaks, a weekly chart from the per-day time, reminders.
- Spaced review of the words met, in the app itself instead of Anki.
- An English voice reading the introduction before each episode.
- Offline listening (downloaded audio).
