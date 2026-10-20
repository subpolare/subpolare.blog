# Image delivery

Article images, including the cover and zoom view, use the existing original
URLs and bytes. Pepic upload settings remain 1800 px / JPEG quality 95.
Only homepage cards use prepared 480 / 960 / 1440 px previews.

The blog reads dimensions from the read-only `/srv/pepic/uploads` volume,
mounted at `/pepic-media`. Rendering does not make HTTP requests. Missing
metadata falls back to the original URL; previews are advertised only after
their files exist. External image URLs are never mapped to local storage.

## Deployment

Commit and push locally, then use `git pull --ff-only` in `/srv/subpolare.blog`.
Use a unique audit filename for each rollout. The audit contains old HTML
caches, post dates and original-file SHA-256 checksums; keep it private and
outside Git and Docker build context.

```sh
docker compose -f docker-compose.production.yml build blog_app
mkdir -p tmp/image-rollout
docker compose -f docker-compose.production.yml run --rm --no-deps \
  -v "$PWD/tmp/image-rollout:/image-rollout" blog_app \
  poetry run python3 manage.py prepare_image_delivery \
  --warm-previews --audit-file /image-rollout/initial.json
docker compose -f docker-compose.production.yml up -d --no-deps blog_app
docker compose -f docker-compose.production.yml run --rm --no-deps \
  -v "$PWD/tmp/image-rollout:/image-rollout" blog_app \
  poetry run python3 manage.py prepare_image_delivery \
  --refresh-cache --audit-file /image-rollout/initial.json
```

Run the same command with `--verify` after rollout to check originals, text,
image URLs and dates again. Cache refresh uses `QuerySet.update`, never
`Post.save`, and does not affect view counts or publication dates.
Warm new homepage covers before publishing them; unprepared covers safely
use the original until the next preparation run.

## Host configuration

Host `/etc` changes require separate authorization from application deployment.
The tracked `etc/nginx/media.subpolare.ru.conf` adds immutable caching only to
successful hashed image responses. Back up the active config before installing,
run `nginx -t`, then reload; restore the backup if validation fails.
The Certbot hook in `etc/letsencrypt/renewal-hooks/deploy/` tests and reloads
nginx after successful renewal of either blog certificate. Install it executable.

## Preview versions and rollback

`PREVIEW_VERSION` is part of preview URLs. Never change compression settings
or replace existing derivatives under an already published version. If resizing
parameters change, use a new derivative namespace and update the version/URL
builder together; Pepic's current on-disk cache is keyed only by length.

To roll back, deploy the preceding Git revision and restore `html_cache` from
the audit using `QuerySet.update`. Restore the backed-up nginx config if needed,
then test and reload nginx. Existing originals and links require no restoration.

## Validation

Run Django offline tests and the frontend tests, plus `git diff --check`.
Compare desktop/mobile and light/dark views of the homepage, article cover,
portrait/landscape images, captions and zoom. Check native lazy loading before
scrolling, intrinsic aspect ratios, original image URLs, prepared `currentSrc`,
cache headers on successful images and absence on error/HTML responses.
Geographic network performance requires real probes in each intended region.
