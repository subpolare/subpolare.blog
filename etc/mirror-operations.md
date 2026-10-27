# RU → COM mirror

RU: `ssh blog`, COM: `ssh netcup`. Both checkouts are `/srv/subpolare.blog`;
Pepic is `/srv/pepic`. Main branch and Compose project: `main`, `subpolareblog`.
Deploy policy: `.agents/skills/deploy/SKILL.md`.

## Trust boundaries

- RU remains the only writer of `posts`, `clickers`, `map_mapplace`, and `map_mapmarker`.
- PostgreSQL logical publication `blog_content` sends committed changes immediately.
  `mirrors_localpostviews`, users, sessions and permissions are not published.
- COM's application uses `blog_reader`, with read access to shared content and
  writes only to local counters and local sessions. Schema updates use a separate
  owner credential via `python3 utils/mirror-db-owner.py migrate --noinput`.
- COM PostgreSQL has **no published ports**. RU's existing 54324 is loopback only.
- `ru_tunnel` connects to RU SSH using `secrets/tunnel/ru_tunnel` with a pinned
  host key. RU accepts this key only from `5.181.51.194`, denies shell access,
  and permits forwarding only to `127.0.0.1:54324` and `127.0.0.1:8022`.
  An SSH Match rule disables reverse forwarding for this peer.
- RU media sync uses a different key `secrets/media/media_sync`. COM accepts it
  only from `92.51.38.155`, with `restrict` and the forced command
  `/usr/bin/python3 /srv/subpolare.blog/etc/ssh/mirror-media-receive.py`.
  The receiver accepts only `uploads`, `legacy-images`, `legacy-videos` selectors
  and runs `rrsync -wo -no-del -munge` under their separate real data directories.
  No key can write `/srv/pepic/.env`, application source, or the receiver itself.
  No shell, tunnels, downloads or deletion operations.
- Maintenance workers receive no database credentials. RU media synchronization
  receives only its own database password, never `BLOG_DATABASE_PASSWORD`.
- Replication secrets never enter Git, Docker images or logs. No service mounts
  the Docker socket. Existing administrative SSH access is independent.

## Synchronization and failure behavior

`blog_media_sync` listens for committed content changes and filesystem writes,
coalesces events for two seconds, and reconciles files every 60 seconds. It also
syncs at startup and retries failures. RU originals and prepared sizes arrive in
`/srv/pepic/uploads`; old storage is copied under `/srv/pepic/legacy`.
Only after a successful full transfer is `uploads/.mirror-synced` updated.
Unreferenced files are retained; this is intentional, not a deletion mirror.

COM health reports readability separately from freshness. Automatic routing
requires all subscription tables ready, an active apply worker with a received
message in the last 120 seconds, and a successful media marker younger than
180 seconds. Failed freshness returns 503 with `Cache-Control: no-store`;
ordinary article reads remain available. Maintenance checks independently of
GeoIP downloads, writes `runtime/local.json`, and logs transitions to an ALERT
state. Inspect these signals with the existing monitoring; no external alert
delivery is configured by this change.

COM reads local PostgreSQL and local media while RU is down. Local view counts
continue. Reactions go through the private tunnel to RU and return 503 during
outages. Editing always uses RU; COM rejects writes to admin/editor routes.
There is no automatic promotion of COM or bidirectional content replication.

Logical replication does not copy schemas/sequences. Apply additive migrations
to COM first, then RU. Incompatible schema changes need an explicit coordinated
deployment plan. Monitor `pg_stat_subscription` on COM and
`pg_replication_slots` on RU; WAL retention is bounded at 1 GiB. An invalidated
slot requires a deliberate resync, never silent data replacement.

## Geo routing

`GEO_REDIRECT_ENABLED` is a per-instance kill switch. RU IPs prefer RU, other
known countries prefer COM; unknown IPs stay put. Manual mirror cookies override
GeoIP. Health state older than 120 seconds suppresses automatic redirects.
Signed arrival markers suppress loops without trusting arbitrary country headers.
Country data is [DB-IP Lite](https://db-ip.com) (CC BY 4.0), updated daily;
Google/Bing crawler ranges are fetched from their official HTTPS endpoints.
Only public navigation is redirected; POST, administration, APIs, static/media,
robots and sitemaps are excluded. A failed first connection cannot be rescued
by an HTTP redirect. GeoDNS is not part of this deployment.

COM Nginx exposes only 80/443 and proxies owned media under `/media/`.
Certbot renews using a webroot and signals Nginx through the ACME volume.
The reverse proxy checks its configuration before reloading.
Nginx runs as the foreground main process so its exit restarts the container.

## Pepic security patch

Both servers use `pepic-hardened:1`. RU retains its existing Compose project
`pepic` and `/srv/pepic/docker-compose.yml`; COM uses the blog Compose project.
`python3 utils/build-pepic.py`, run from `/srv/subpolare.blog`, copies only source
files from `/srv/pepic` into a disposable build directory, checks/applies
`etc/pepic/security.patch`, and runs the storage/handler Go regression tests
before producing the image. It never changes the Pepic source checkout or media.
Build on RU and copy the tested image to COM. Recreate the two Pepic containers
only when deploying this patch or a subsequent intentional Pepic update.

Storage errors return to callers instead of terminating the process. Dynamic
derivatives accept only 480, 960 and 1440 pixels, with at most two concurrent
cache-miss conversions; originals, full URLs and image-processing quality are
unchanged. Existing media files are not regenerated. Requests at or above the
configured original length still serve the original without processing.

## Verification

- `curl --fail https://subpolare.com/_mirror/health` and the RU equivalent.
- Inspect logs of `blog_media_sync`, `ru_tunnel`, `blog_maintenance` and Nginx.
- Check content/table counts and replica apply state, not just container status.
- `docker ps` / `ss -lnt` must show no public PostgreSQL port.
- Negative SSH tests: both sync keys must reject `whoami`; the tunnel key must
  reject any destination other than the two permitted loopback ports.
- Use independent temporary databases for write/replication tests; do not insert
  synthetic posts or reactions on production.
