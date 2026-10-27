#!/bin/sh
set -eu
nginx -t
(
    while sleep 30; do
        if test -f /var/www/acme/reload; then
            nginx -t && nginx -s reload && rm /var/www/acme/reload
        fi
    done
) &
# The container must exit when the web server exits; Docker then restarts it.
exec nginx -g 'daemon off;'
