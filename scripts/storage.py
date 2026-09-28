#!/usr/bin/env python3
"""Keep chapter audio in Cloudflare R2 (the course's permanent audio store; git holds no audio).

    python3 scripts/storage.py status               # what's stored, what's only local
    python3 scripts/storage.py push s01e01 [...]    # upload chapter.mp3 + timing.json
    python3 scripts/storage.py push --all           # every chapter that has local audio
    python3 scripts/storage.py pull s01e01 [...]    # download them into chapters/<id>/audio/
    python3 scripts/storage.py pull --all

make_audio.py pushes each chapter as soon as its audio is made. In the bucket a chapter's files are
audio/<id>/chapter.mp3 and audio/<id>/timing.json. The raw clips (chapters/<id>/audio/clips/, about
250 MB a chapter) stay local only: re-making a chapter's audio after a new session costs a full run.

Needs these environment variables (set in the environment's settings, never in the repo):
    R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, and optionally R2_BUCKET
    (default "input-masters-italian"). The host <account id>.r2.cloudflarestorage.com must be
allowed by the environment's network policy. Plain standard library: R2 speaks the S3 API, and
requests are signed with AWS Signature Version 4.
"""
import datetime
import hashlib
import hmac
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ("chapter.mp3", "timing.json")
TYPES = {".mp3": "audio/mpeg", ".json": "application/json"}


def configured():
    return all(os.environ.get(k) for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"))


def _cfg():
    if not configured():
        raise SystemExit("R2 isn't set up: add R2_ACCOUNT_ID, R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY "
                         "to the environment's variables (see this script's docstring).")
    return (os.environ["R2_ACCOUNT_ID"], os.environ["R2_ACCESS_KEY_ID"], os.environ["R2_SECRET_ACCESS_KEY"],
            os.environ.get("R2_BUCKET", "input-masters-italian"))


def _request(method, key="", body=b"", query=None, content_type=None):
    account, access, secret, bucket = _cfg()
    host = f"{account}.r2.cloudflarestorage.com"
    path = "/" + bucket + ("/" + urllib.parse.quote(key) if key else "")
    qs = "&".join(f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
                  for k, v in sorted((query or {}).items()))
    now = datetime.datetime.now(datetime.timezone.utc)
    amz_date, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body).hexdigest()
    headers = {"host": host, "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date}
    if content_type:
        headers["content-type"] = content_type
    signed = ";".join(sorted(headers))
    canonical = "\n".join([method, path, qs, "".join(f"{k}:{headers[k]}\n" for k in sorted(headers)),
                           signed, payload_hash])
    scope = f"{day}/auto/s3/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    k = ("AWS4" + secret).encode()
    for part in (day, "auto", "s3", "aws4_request"):
        k = hmac.new(k, part.encode(), hashlib.sha256).digest()
    sig = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
    headers["authorization"] = f"AWS4-HMAC-SHA256 Credential={access}/{scope}, SignedHeaders={signed}, Signature={sig}"
    req = urllib.request.Request(f"https://{host}{path}" + (f"?{qs}" if qs else ""), data=body or None,
                                 method=method, headers={k: v for k, v in headers.items() if k != "host"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code < 500 or attempt == 3:
                raise SystemExit(f"R2 {method} {key or bucket}: HTTP {e.code} {e.read()[:300].decode(errors='replace')}")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt == 3:
                raise SystemExit(f"R2 {method} {key or bucket}: {e}")


def stored():
    """{chapter id: {file name: size}} for everything in the bucket."""
    out, token = {}, None
    while True:
        q = {"list-type": 2, "prefix": "audio/"}
        if token:
            q["continuation-token"] = token
        xml = (_request("GET", query=q) or b"").decode()
        for key, size in re.findall(r"<Key>(.*?)</Key>.*?<Size>(\d+)</Size>", xml, re.S):
            m = re.match(r"audio/([^/]+)/(.+)$", key)
            if m:
                out.setdefault(m.group(1), {})[m.group(2)] = int(size)
        token = (re.search(r"<NextContinuationToken>(.*?)</NextContinuationToken>", xml) or [None, None])[1]
        if not token:
            return out


def push(cid):
    folder = ROOT / "chapters" / cid / "audio"
    missing = [f for f in FILES if not (folder / f).exists()]
    if missing:
        print(f"{cid}: no local {', '.join(missing)}; nothing pushed")
        return False
    for f in FILES:
        p = folder / f
        _request("PUT", f"audio/{cid}/{f}", p.read_bytes(), content_type=TYPES[p.suffix])
    print(f"{cid}: pushed chapter.mp3 ({(folder / 'chapter.mp3').stat().st_size / 1e6:.1f} MB) and timing.json")
    return True


def pull(cid):
    folder = ROOT / "chapters" / cid / "audio"
    got = {f: _request("GET", f"audio/{cid}/{f}") for f in FILES}
    if any(v is None for v in got.values()):
        print(f"{cid}: not in storage")
        return False
    folder.mkdir(parents=True, exist_ok=True)
    for f, data in got.items():
        (folder / f).write_bytes(data)
    print(f"{cid}: pulled into chapters/{cid}/audio/")
    return True


def local_ids():
    return sorted(p.parent.parent.name for p in ROOT.glob("chapters/*/audio/chapter.mp3"))


def main(argv):
    if not argv or argv[0] not in ("status", "push", "pull"):
        print(__doc__)
        return 2
    cmd, ids = argv[0], argv[1:]
    if cmd == "status":
        remote, local = stored(), set(local_ids())
        for cid in sorted(set(remote) | local):
            where = ("stored" if all(f in remote.get(cid, {}) for f in FILES) else "partly stored" if cid in remote
                     else "LOCAL ONLY") + (" + local" if cid in local and cid in remote else "")
            mb = remote.get(cid, {}).get("chapter.mp3", 0) / 1e6
            print(f"{cid}  {where}{f'  {mb:.1f} MB' if mb else ''}")
        print(f"{len(remote)} chapter(s) in storage, {len(local - set(remote))} only in this workspace")
        return 0
    if ids == ["--all"]:
        ids = local_ids() if cmd == "push" else sorted(stored())
    ok = all([(push if cmd == "push" else pull)(cid) for cid in ids])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
