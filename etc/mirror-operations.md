# RU → COM mirror

RU: `ssh blog`, COM: `ssh netcup`. Both checkouts are `/srv/subpolare.blog`;
Pepic is `/srv/pepic`. Main branch and Compose project: `main`, `subpolareblog`.
Deploy policy: `.agents/skills/deploy/SKILL.md`.

## Trust boundaries

- RU remains the only writer of `posts`, `clickers`, `map_mapplace`, `map_mapmarker`,
  and canonical `mirrors_postviewtotals`.
- PostgreSQL logical publication `blog_content` sends committed changes immediately.
  `mirrors_localpostviews`, users, sessions and permissions are not published.
- COM's application uses `blog_reader`, with read access to shared content and
  writes only to local cumulative counters and local sessions. Schema updates use a separate
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
continue and are delivered to RU after recovery. The displayed total remains
the last replicated RU value. Reactions go through the private tunnel to RU and return 503 during
outages. Editing always uses RU; COM rejects writes to admin/editor routes.
There is no automatic promotion of COM or bidirectional content replication.

Logical replication does not copy schemas/sequences. Apply additive migrations
to COM first, then RU. Incompatible schema changes need an explicit coordinated
deployment plan. Monitor `pg_stat_subscription` on COM and
`pg_replication_slots` on RU; WAL retention is bounded at 1 GiB. An invalidated
slot requires a deliberate resync, never silent data replacement.

## Shared view counts

`mirrors_localpostviews` remains an independent, durable cumulative counter on
each server. Only RU writes `mirrors_postviewtotals`, which stores the highest
accepted RU count and new COM views since activation for every article. Their sum is used in all article
templates and the admin. The old `posts.view_count` is legacy data, not a live
counter. Content saves cannot overwrite analytics. View updates do not trigger
media synchronization.

RU updates its own contribution in the same database transaction as the local
increment. COM's `blog_views_sync` sends batches of up to 250 signed snapshots
every 15 seconds through `ru_tunnel:8022/_mirror/views`. It uses the existing
shared `MIRROR_SIGNING_KEY`, a separate signing salt, and a five-minute signature
lifetime. Keep clocks synchronized. There is no browser request to RU and no
transfer of reader IPs, cookies or identities. Article requests never wait on
the network. Repeated, concurrent or reordered snapshots are merged with
`GREATEST`; neither retries nor a lost acknowledgement can add duplicate views.
COM cannot write the canonical table. PostgreSQL replication delivers RU's
accepted total back to COM. The usual lag is one worker interval plus network
and replication time; this is not instantaneous consistency during an outage.

The existing RU total is preserved. Migration 0003 captures each COM local count
in `mirrors_mirrorviewbaseline`; those historical COM reads are **not added** to
RU. Only `local count - baseline` is sent, starting from zero at activation.
Posts first read after activation have a zero baseline. The baseline is local,
unreplicated and read-only for the application. Its migration refuses to proceed
if COM views have already been accepted by RU, preventing an unsafe rebase.

All adjusted snapshots are periodically resent. Neither local counters nor their
baselines may be truncated or reset after delivery. Do not seed COM's local
counter from a new RU backup. After restoring an older COM database, preserve or
recover its latest counters and baselines before resuming reads; otherwise new
views below RU's last accepted COM high-water mark are hidden.

### First rollout of shared views

This is an additive schema change **and an explicit replication configuration
change**, not just a normal application restart. Use existing owner credentials;
no new secrets, users, tunnels or direct PostgreSQL access from the app are needed.
Build both images first. In `/srv/subpolare.blog` on the respective servers:

1. COM: `python3 utils/mirror-db-owner.py migrate --noinput`. Migration 0002
   creates an empty totals table; migration 0003 records the COM starting point.
   Both preserve all local counts. New COM views begin accumulating at this step.
2. RU: update `blog_app` normally. Its startup migration seeds totals from RU's
   existing local counters. Wait for the new application to be ready.
3. RU: `docker compose -p subpolareblog -f docker-compose.production.yml exec -T
   blog_app python3 manage.py configure_view_replication`. This reconciles any
   local reads during migration, grants replication SELECT access, and adds
   the totals table to the existing publication. It is safe to repeat.
4. COM: `python3 utils/mirror-db-owner.py configure_view_replication`. This grants
   the reader SELECT access to totals and baselines and refreshes the subscription, copying
   totals from RU. It refuses a nonempty, unregistered target table. Wait until
   the new `pg_subscription_rel` entry is ready (`srsubstate = 'r'`).
5. COM: update `blog_app blog_maintenance blog_views_sync` with Compose
   `up -d --no-deps`. The new worker delivers only COM reads since step 1.
   Future deployments must recreate `blog_views_sync` along with the app.
6. Check worker logs for failure/recovery messages, both health endpoints, and
   read-only totals on RU/COM. In a quiet interval, `ru_count` and `com_count`
   must match on both servers; on RU `com_count` should catch up with COM's
   local counter minus its baseline. Active traffic can account for one interval
   of difference.

For a one-shot retry on COM, run `python3 manage.py mirror_views_sync --once`
inside `blog_views_sync`. A failure exits nonzero and keeps every local count.
On RU, the same command reconciles RU history without making network requests.
New installations use `configure_mirror_database` as before; its publication
already includes the totals table.

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
