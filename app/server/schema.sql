-- Input Masters · Italian: the app's database (PostgreSQL, e.g. Replit's built-in database).
-- Built from docs/app-spec.md §3 (time counting), §4 (progress per user) and §5 (subscription).
-- Safe to run more than once: it only creates what's missing.
--
-- Rules the app code must keep (they aren't all enforceable here):
--   * Time only ever goes UP, by batches the server has checked (§3): never overwrite a total
--     with a number from the browser. Use add_time() below; it caps each batch.
--   * Access comes only from Stripe's webhooks (§5): the browser never writes subscriptions.
--   * Deleting a user deletes everything of theirs (ON DELETE CASCADE): that's account deletion.

-- One row per learner. id is Clerk's user id (e.g. "user_2abc...").
CREATE TABLE IF NOT EXISTS users (
  id              text PRIMARY KEY,
  email           text NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  started         boolean NOT NULL DEFAULT false,      -- has opened the library at least once
  last_chapter    text,                                -- "Pick up where you left off", e.g. 's01e02'
  speed           real NOT NULL DEFAULT 1.0 CHECK (speed BETWEEN 0.5 AND 2.0),   -- playback speed
  english_under   boolean NOT NULL DEFAULT false,      -- "English under every sentence"
  last_time_batch timestamptz                          -- when the last time batch arrived (caps the next one)
);

-- The learner's Stripe subscription, as Stripe's webhooks last reported it.
CREATE TABLE IF NOT EXISTS subscriptions (
  user_id                text PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  stripe_customer_id     text UNIQUE NOT NULL,
  stripe_subscription_id text UNIQUE,
  status                 text NOT NULL DEFAULT 'none',  -- Stripe's status: active, past_due, canceled, unpaid, incomplete…
  plan                   text CHECK (plan IN ('monthly', 'yearly')),
  current_period_end     timestamptz,                    -- paid up to here
  cancel_at_period_end   boolean NOT NULL DEFAULT false, -- cancelled, access continues to current_period_end
  stripe_event_at        timestamptz,                    -- time of the Stripe event last applied (ignore older ones)
  updated_at             timestamptz NOT NULL DEFAULT now()
);

-- Stripe can send the same webhook twice: record each event id and skip repeats.
CREATE TABLE IF NOT EXISTS stripe_events (
  id          text PRIMARY KEY,                          -- Stripe's event id, "evt_..."
  type        text NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now()
);

-- Progress in one chapter.
CREATE TABLE IF NOT EXISTS chapter_progress (
  user_id    text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  chapter_id text NOT NULL,                              -- e.g. 's01e02'
  read_s     integer NOT NULL DEFAULT 0 CHECK (read_s >= 0),     -- seconds reading
  listen_s   integer NOT NULL DEFAULT 0 CHECK (listen_s >= 0),   -- seconds listening
  tab        text,                                       -- tab last open: story, side, vocab, grammar
  at_segment text,                                       -- sentence id of the reading place
  far        integer NOT NULL DEFAULT -1,                -- furthest sentence index reached (for % read)
  played     jsonb NOT NULL DEFAULT '{}'::jsonb,         -- {segment id: last word index heard}
  audio_t    real NOT NULL DEFAULT 0,                    -- audio position to resume from, seconds
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, chapter_id)
);

-- Time per day, for "this week" and later streaks and charts. day is the learner's local date.
CREATE TABLE IF NOT EXISTS daily_time (
  user_id  text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  day      date NOT NULL,
  read_s   integer NOT NULL DEFAULT 0 CHECK (read_s >= 0),
  listen_s integer NOT NULL DEFAULT 0 CHECK (listen_s >= 0),
  PRIMARY KEY (user_id, day)
);

-- Vocabulary items ticked "I know it".
CREATE TABLE IF NOT EXISTS known_words (
  user_id  text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  vocab_id text NOT NULL,
  added_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, vocab_id)
);

-- Course totals are the sum of the chapters, so they can never disagree with them.
CREATE OR REPLACE VIEW user_totals AS
  SELECT u.id AS user_id,
         COALESCE(SUM(p.read_s), 0)   AS read_s,
         COALESCE(SUM(p.listen_s), 0) AS listen_s
  FROM users u LEFT JOIN chapter_progress p ON p.user_id = u.id
  GROUP BY u.id;

-- Who has the full course: an active subscription, or one in Stripe's card-retry period.
-- A cancelled subscription stays 'active' until its period ends, then Stripe marks it 'canceled'.
CREATE OR REPLACE FUNCTION has_full_course(uid text) RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT EXISTS (SELECT 1 FROM subscriptions WHERE user_id = uid AND status IN ('active', 'past_due'));
$$;

-- Add one time batch from the browser (§3). Each part is capped at the time since the previous
-- batch (plus 5 s of slack), and at 120 s when there was no previous batch. The learner's local
-- date is accepted only within a day of the server's. Adds to the chapter and to the day.
-- Returns the seconds actually added: (read, listen).
CREATE OR REPLACE FUNCTION add_time(uid text, chapter text, local_day date, read_in integer, listen_in integer,
                                    OUT read_added integer, OUT listen_added integer)
LANGUAGE plpgsql AS $$
DECLARE
  prev timestamptz;
  cap  integer;
BEGIN
  SELECT last_time_batch INTO prev FROM users WHERE id = uid FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'unknown user %', uid;
  END IF;
  cap := CASE WHEN prev IS NULL THEN 120
              ELSE LEAST(3600, CEIL(EXTRACT(EPOCH FROM now() - prev))::integer + 5) END;
  read_added   := GREATEST(0, LEAST(COALESCE(read_in, 0), cap));
  listen_added := GREATEST(0, LEAST(COALESCE(listen_in, 0), cap));
  IF local_day IS NULL OR abs(local_day - current_date) > 1 THEN
    local_day := current_date;
  END IF;

  UPDATE users SET last_time_batch = now() WHERE id = uid;
  IF read_added = 0 AND listen_added = 0 THEN
    RETURN;
  END IF;
  INSERT INTO chapter_progress (user_id, chapter_id, read_s, listen_s)
    VALUES (uid, chapter, read_added, listen_added)
    ON CONFLICT (user_id, chapter_id) DO UPDATE
      SET read_s = chapter_progress.read_s + EXCLUDED.read_s,
          listen_s = chapter_progress.listen_s + EXCLUDED.listen_s,
          updated_at = now();
  INSERT INTO daily_time (user_id, day, read_s, listen_s)
    VALUES (uid, local_day, read_added, listen_added)
    ON CONFLICT (user_id, day) DO UPDATE
      SET read_s = daily_time.read_s + EXCLUDED.read_s,
          listen_s = daily_time.listen_s + EXCLUDED.listen_s;
END;
$$;
