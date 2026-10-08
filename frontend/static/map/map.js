(function (root, factory) {
    const api = factory();
    if (typeof module === "object" && module.exports) module.exports = api;
    else root.ArticleMap = api;
})(typeof window === "undefined" ? globalThis : window, function () {
    "use strict";

    function minimumWorldZoom(size) {
        // EPSG:4326 spans 512 × 256 pixels at zoom zero.
        return Math.max(0, Math.log2(Math.max(size.x / 512, size.y / 256)));
    }

    function wrapLongitude(longitude) {
        return ((longitude + 180) % 360 + 360) % 360 - 180;
    }

    function groupMarkers(markers) {
        const groups = new Map();
        markers.forEach(function (marker) {
            // Inputs are already geographic coordinates. Arithmetic wrapping
            // would round very close but distinct longitudes into one group.
            const longitude = marker.longitude === 180 ? -180 : marker.longitude;
            const key = marker.latitude + ":" + longitude;
            if (!groups.has(key)) groups.set(key, []);
            groups.get(key).push(marker);
        });
        return Array.from(groups.values());
    }

    function cityName(city, language) {
        return (language === "ru" ? city.ru : city.en) || city.en || city.ru || "";
    }

    function safeURL(value, origin) {
        try {
            if (!value || /[\s\\\u0000-\u001f\u007f]/.test(value) || value.startsWith("//")) return null;
            if (!value.startsWith("/") && !/^https?:\/\//i.test(value)) return null;
            const url = new URL(value, origin);
            return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password ? url.href : null;
        } catch (error) { return null; }
    }

    function markerElement(doc, item, large, count, origin) {
        const node = doc.createElement(count ? "button" : "a");
        node.className = "map-marker" + (large ? " map-marker-large" : "");
        node.style.setProperty("--marker-color", /^#[0-9a-f]{6}$/i.test(item.color) ? item.color : "#333333");
        if (count) {
            node.type = "button";
            node.textContent = String(count);
            node.setAttribute("aria-label", String(count));
            node.setAttribute("aria-expanded", "false");
        } else {
            node.href = safeURL(item.url, origin) || "#";
            node.target = "_self";
            node.setAttribute("hx-boost", "false");
            node.setAttribute("aria-label", item.title);
            const img = doc.createElement("img");
            // Never use a cover URL from the article, only the local thumbnail endpoint.
            const preview = safeURL(item.preview, origin);
            if (preview && new URL(preview).origin === origin && new URL(preview).pathname.startsWith("/map/previews/")) img.src = preview;
            img.alt = "";
            img.width = 128;
            img.height = 128;
            img.decoding = "async";
            img.addEventListener("error", function () { img.remove(); }, {once: true});
            node.appendChild(img);
        }
        const label = doc.createElement("span");
        label.className = "map-marker-title";
        label.textContent = count ? String(count) : item.title;
        node.appendChild(label);
        return node;
    }

    async function fetchJSON(url, signal) {
        const response = await fetch(url, {signal: signal, credentials: "same-origin"});
        if (!response.ok) throw new Error("Map data unavailable");
        return response.json();
    }

    async function mount(element, signal) {
        const data = element.dataset;
        const doc = element.ownerDocument;
        const win = doc.defaultView;
        const L = win.L;
        const edit = data.mode === "edit";
        const overview = data.mode === "overview";
        const requestController = new AbortController();
        const abort = function () { requestController.abort(); };
        signal.addEventListener("abort", abort, {once: true});
        const timeout = win.setTimeout(abort, 12000);
        let values;
        try {
            values = await Promise.all([
                fetchJSON(data.land, requestController.signal),
                fetchJSON(data.cities, requestController.signal),
                fetchJSON(data.lakes, requestController.signal),
                fetchJSON(data.rivers, requestController.signal),
                edit ? Promise.resolve([]) : fetchJSON(data.markers, requestController.signal)
            ]);
        } catch (error) {
            requestController.abort();
            throw error;
        } finally {
            win.clearTimeout(timeout);
            signal.removeEventListener("abort", abort);
        }
        if (signal.aborted) throw new Error("Map removed");
        const [land, cities, lakes, rivers, items] = values;
        const worldBounds = L.latLngBounds([[-90, -180], [90, 180]]);
        const map = L.map(element, {
            crs: L.CRS.EPSG4326, preferCanvas: true, maxZoom: 6, minZoom: 0,
            zoomSnap: 0, maxBounds: worldBounds, maxBoundsViscosity: 1,
            scrollWheelZoom: false, touchZoom: true, bounceAtZoomLimits: false,
            dragging: true, keyboard: true, worldCopyJump: false,
            attributionControl: true, zoomControl: true
        });
        const cleaners = [];
        let destroyed = false;
        function destroy() {
            if (destroyed) return;
            destroyed = true;
            cleaners.forEach(clean => clean());
            map.remove();
        }
        try {
            function minimumZoom() {
                // Cover the viewport: neither axis may expose space beyond the
                // single world, including on portrait screens and after resize.
                return minimumWorldZoom(map.getSize());
            }

            function showWorld() {
                map.setView([15, 0], map.getMinZoom(), {animate: false});
            }

            map.setMinZoom(minimumZoom());
            map.attributionControl.setPrefix(false);
            map.attributionControl.addAttribution('<a href="https://www.naturalearthdata.com/" target="_blank" rel="noopener">Natural Earth</a>');
            const language = data.language;
            const worldTitle = language === "ru" ? "Обзор мира" : "World view";
            const WorldControl = L.Control.extend({
                options: {position: "topleft"},
                onAdd: function () {
                    const box = L.DomUtil.create("div", "leaflet-bar map-world-control");
                    const button = doc.createElement("button");
                    button.type = "button";
                    button.textContent = "↺";
                    button.title = worldTitle;
                    button.setAttribute("aria-label", worldTitle);
                    button.addEventListener("click", showWorld);
                    box.appendChild(button);
                    L.DomEvent.disableClickPropagation(box);
                    return box;
                }
            });
            map.addControl(new WorldControl());
            showWorld();
            const landLayer = L.layerGroup().addTo(map);
            const markerLayer = L.layerGroup().addTo(map);
            const cityLayer = L.layerGroup().addTo(map);
            const connectorLayer = L.layerGroup().addTo(map);
            let expanded;
            let expandedFocus;
            let formMarker;

            function drawGeography() {
                const style = win.getComputedStyle(element);
                const color = name => style.getPropertyValue(name).trim();
                landLayer.clearLayers();
                L.geoJSON(land, {interactive: false, style: {
                    fillColor: color("--map-land"), color: color("--map-coast"), weight: 0.65, fillOpacity: 1
                }}).addTo(landLayer);
                L.geoJSON(rivers, {interactive: false, style: {
                    color: color("--map-river"), weight: 1, opacity: 0.85
                }}).addTo(landLayer);
                L.geoJSON(lakes, {interactive: false, style: {
                    fillColor: color("--map-water"), color: color("--map-river"), weight: 0.5, fillOpacity: 1
                }}).addTo(landLayer);
                drawCities();
            }

            function pointFor(latitude, longitude) {
                return L.latLng(latitude, longitude);
            }

            function inView(point, padding) {
                const pixel = map.latLngToContainerPoint(point);
                const size = map.getSize();
                return pixel.x >= -padding && pixel.y >= -padding && pixel.x <= size.x + padding && pixel.y <= size.y + padding;
            }

            function addMarker(item, position, count, onClick) {
                const large = map.getZoom() >= 4;
                const diameter = large ? 46 : 26;
                const node = markerElement(doc, item, large, count, win.location.origin);
                // An actual anchor handles Enter and a single tap, in the current tab.
                L.DomEvent.disableClickPropagation(node);
                if (onClick) node.addEventListener("click", onClick);
                L.marker(position, {icon: L.divIcon({html: node, className: "map-marker-host", iconSize: [diameter, diameter], iconAnchor: [diameter / 2, diameter / 2]}), keyboard: false, bubblingMouseEvents: false}).addTo(markerLayer);
                return node;
            }

            function drawMarkers() {
                markerLayer.clearLayers();
                connectorLayer.clearLayers();
                groupMarkers(items).forEach(function (group) {
                    const item = group[0];
                    const origin = pointFor(item.latitude, item.longitude);
                    const key = item.id;
                    if (!inView(origin, 0) && expanded !== key) return;
                    if (group.length === 1) { addMarker(item, origin); return; }
                    if (inView(origin, 0)) {
                        const groupNode = addMarker(item, origin, group.length, function () {
                            expanded = expanded === key ? null : key;
                            expandedFocus = key;
                            if (expanded !== null) map.panTo(origin, {animate: false});
                            if (expandedFocus === key) drawMarkers();
                        });
                        groupNode.setAttribute("aria-label", language === "ru" ? `Раскрыть статьи: ${group.length}` : `Show articles: ${group.length}`);
                        groupNode.setAttribute("aria-expanded", String(expanded === key));
                        if (expanded === null && expandedFocus === key) groupNode.focus({preventScroll: true});
                    }
                    if (expanded !== key) return;
                    const center = map.latLngToContainerPoint(origin);
                    const radius = Math.max(map.getZoom() >= 4 ? 82 : 58, group.length * (map.getZoom() >= 4 ? 76 : 52) / (2 * Math.PI));
                    // Keep the circle anchored to its real point, so even a large
                    // group can be panned into view without changing coordinates.
                    group.forEach(function (member, index) {
                        const angle = index * Math.PI * 2 / group.length - Math.PI / 2;
                        const position = map.containerPointToLatLng([center.x + radius * Math.cos(angle), center.y + radius * Math.sin(angle)]);
                        L.polyline([origin, position], {color: item.color, weight: 1, opacity: 0.5, interactive: false}).addTo(connectorLayer);
                        if (!inView(position, 0)) return;
                        const node = addMarker(member, position);
                        if (expandedFocus === key) {
                            node.focus({preventScroll: true});
                            expandedFocus = false;
                        }
                    });
                });
                expandedFocus = false;
            }

            function drawCities() {
                cityLayer.clearLayers();
                const color = win.getComputedStyle(element).getPropertyValue("--map-label").trim();
                cities.forEach(function (city) {
                    const position = pointFor(city.coordinates[1], city.coordinates[0]);
                    L.circleMarker(position, {
                        radius: 1.75, stroke: false, fillColor: color, fillOpacity: 0.5, interactive: false
                    }).addTo(cityLayer);
                });
            }

            function redraw() { if (edit) updateFormMarker(); else drawMarkers(); }
            map.on("moveend resize", redraw);
            map.on("click", function (event) {
                if (overview) {
                    const url = new URL(data.add, win.location.origin);
                    url.searchParams.set("latitude", Math.max(-90, Math.min(90, event.latlng.lat)).toFixed(6));
                    url.searchParams.set("longitude", wrapLongitude(event.latlng.lng).toFixed(6));
                    win.location.assign(url.href);
                } else if (edit) setFields(event.latlng);
                else if (expanded != null) { expanded = null; drawMarkers(); }
            });

            function listen(target, name, handler) {
                target.addEventListener(name, handler);
                cleaners.push(function () { target.removeEventListener(name, handler); });
            }

            const latInput = edit ? doc.getElementById("id_latitude") : null;
            const lngInput = edit ? doc.getElementById("id_longitude") : null;
            function setFields(position) {
                latInput.value = Math.max(-90, Math.min(90, position.lat)).toFixed(6);
                lngInput.value = wrapLongitude(position.lng).toFixed(6);
                updateFormMarker();
            }

            function updateFormMarker() {
                const lat = Number(latInput.value), lng = Number(lngInput.value);
                if (!latInput.value || !lngInput.value || !Number.isFinite(lat) || !Number.isFinite(lng) || Math.abs(lat) > 90 || Math.abs(lng) > 180) {
                    if (formMarker) { formMarker.remove(); formMarker = null; }
                    return;
                }
                const position = pointFor(lat, lng);
                if (formMarker) formMarker.setLatLng(position);
                else {
                    const pin = doc.createElement("span");
                    pin.className = "map-edit-pin";
                    formMarker = L.marker(position, {draggable: true, title: "Перетащить точку", icon: L.divIcon({html: pin, className: "map-edit-host", iconSize: [26, 26], iconAnchor: [13, 13]})}).addTo(map);
                    formMarker.on("dragend", function () { setFields(formMarker.getLatLng()); });
                }
            }

            if (edit) {
                listen(latInput, "input", updateFormMarker);
                listen(lngInput, "input", updateFormMarker);
                updateFormMarker();
                if (formMarker) map.setView(formMarker.getLatLng(), 4);
                const input = doc.getElementById("map-city");
                const results = doc.getElementById("map-city-results");
                listen(input, "keydown", function (event) {
                    if (event.key === "Enter") {
                        event.preventDefault();
                        const first = results.querySelector("button");
                        if (first) first.click();
                    }
                });
                listen(input, "input", function () {
                    results.replaceChildren();
                    const query = input.value.trim().toLocaleLowerCase();
                    if (query.length < 2) return;
                    cities.filter(city => (city.ru + " " + city.en).toLocaleLowerCase().includes(query)).slice(0, 12).forEach(function (city) {
                        const button = doc.createElement("button");
                        button.type = "button";
                        button.textContent = cityName(city, language);
                        button.addEventListener("click", function () {
                            const position = pointFor(city.coordinates[1], city.coordinates[0]);
                            setFields(position);
                            map.setView(position, 5);
                            input.value = cityName(city, language);
                            results.replaceChildren();
                        });
                        results.appendChild(button);
                    });
                });
                cleaners.push(function () { results.replaceChildren(); });
            }

            const themeObserver = new win.MutationObserver(drawGeography);
            themeObserver.observe(doc.documentElement, {attributes: true, attributeFilter: ["theme", "data-theme"]});
            cleaners.push(function () { themeObserver.disconnect(); });
            const preference = win.matchMedia("(prefers-color-scheme: dark)");
            listen(preference, "change", drawGeography);
            const resize = new win.ResizeObserver(function () {
                const wasWorldView = Math.abs(map.getZoom() - map.getMinZoom()) < 0.001;
                map.invalidateSize({pan: false});
                map.setMinZoom(minimumZoom());
                if (wasWorldView) showWorld();
                else map.panInsideBounds(worldBounds, {animate: false});
            });
            resize.observe(element);
            cleaners.push(function () { resize.disconnect(); });
            drawGeography();
            redraw();
            return {destroy: destroy};
        } catch (error) {
            destroy();
            throw error;
        }
    }

    return {mount: mount, minimumWorldZoom: minimumWorldZoom, wrapLongitude: wrapLongitude,
        groupMarkers: groupMarkers, cityName: cityName,
        safeURL: safeURL, markerElement: markerElement};
});
