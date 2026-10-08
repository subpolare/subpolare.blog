const {test} = require("node:test");
const assert = require("node:assert/strict");
const api = require("../static/map/map.js");
const loader = require("../static/map/loader.js");

function node(tag) {
    return {
        tag, children: [], attributes: {}, events: {}, hidden: false,
        style: {setProperty(name, value) { this[name] = value; }},
        appendChild(child) { this.children.push(child); },
        replaceChildren() { this.children = []; },
        setAttribute(name, value) { this.attributes[name] = value; },
        addEventListener(name, callback) { this.events[name] = callback; },
        remove() { this.removed = true; }
    };
}

test("exact coordinate matches group together, including both sides of the date line", () => {
    const markers = [{id: 1, latitude: 1, longitude: 180}, {id: 2, latitude: 1, longitude: -180}, {id: 3, latitude: 1, longitude: 179.9999}];
    const original = JSON.stringify(markers);
    assert.deepEqual(api.groupMarkers(markers).map(group => group.map(item => item.id)), [[1, 2], [3]]);
    assert.equal(JSON.stringify(markers), original);
    assert.equal(api.wrapLongitude(541), -179);
    assert.equal(api.groupMarkers([{latitude: 0, longitude: 0}, {latitude: 0, longitude: 1e-15}]).length, 2);
});

test("city language fallback remains available for the admin search", () => {
    const cities = [
        {ru: "Москва", en: "Moscow", population: 6000000, rank: 2},
        {ru: "", en: "Small city", population: 999999, rank: 1},
        {ru: "Средний", en: "Medium", population: 1000000, rank: 1},
        {ru: "Большой", en: "Large", population: 5000000, rank: 1}
    ];
    assert.equal(api.cityName(cities[0], "ru"), "Москва");
    assert.equal(api.cityName(cities[0], "es"), "Moscow");
    assert.equal(api.cityName(cities[1], "ru"), "Small city");
});

test("minimum zoom fits the entire world in wide and square viewports", () => {
    for (const size of [{x: 1440, y: 576}, {x: 390, y: 390}, {x: 2560, y: 1024}, {x: 320, y: 320}]) {
        const scale = 2 ** api.minimumWorldZoom(size);
        assert.ok(512 * scale <= size.x + 1e-9);
        assert.ok(256 * scale <= size.y + 1e-9);
        assert.ok(Math.abs(512 * scale - size.x) < 1e-9 || Math.abs(256 * scale - size.y) < 1e-9);
    }
    assert.ok(api.minimumWorldZoom({x: 800, y: 560}) < api.minimumWorldZoom({x: 2560, y: 560}));
});

test("mobile overview fits every article with padding, including distant points", () => {
    const size = {x: 390, y: 390};
    for (const items of [
        [{latitude: 55.75, longitude: 37.6}, {latitude: 69.16, longitude: 35.14}],
        [{latitude: -85, longitude: -179}, {latitude: 85, longitude: 179}],
        [{latitude: 10, longitude: 100}]
    ]) {
        const view = api.initialView(size, items, true);
        assert.ok(Number.isFinite(view.zoom));
        for (const item of items) {
            const x = size.x / 2 + (item.longitude - view.center[1]) * 512 / 360 * 2 ** view.zoom;
            assert.ok(x >= 64 - 1e-9 && x <= size.x - 36 + 1e-9);
            assert.ok(Math.abs(item.latitude - view.center[0]) * 256 / 180 * 2 ** view.zoom <= size.y / 2 - 36 + 1e-9);
        }
    }
    assert.deepEqual(api.initialView(size, [], true), {center: [0, 0], zoom: api.minimumWorldZoom(size)});
    assert.equal(api.zoomPercentage(2.3, 2.3), 100);
    assert.equal(api.zoomPercentage(3.3, 2.3), 200);
    assert.equal(api.zoomPercentage(1.3, 2.3), 50);
});

function trackpad() {
    const events = {}, frames = new Map(), changes = [];
    let zoom = 1, next = 0;
    const element = {
        addEventListener(name, callback, options) { events[name] = callback; assert.equal(options.passive, false); },
        removeEventListener(name) { delete events[name]; }
    };
    const win = {
        requestAnimationFrame(callback) { frames.set(++next, callback); return next; },
        cancelAnimationFrame(id) { frames.delete(id); }
    };
    const map = {
        getZoom: () => zoom, getMinZoom: () => -1, getMaxZoom: () => 6,
        getSize: () => ({x: 390, y: 390}),
        mouseEventToContainerPoint: event => [event.clientX, event.clientY],
        setZoomAround(point, value) { zoom = value; changes.push({point, zoom}); }
    };
    const destroy = api.installTrackpadZoom(element, map, win);
    return {events, frames, changes, destroy, map,
        event(extra) { return Object.assign({clientX: 140, clientY: 120, deltaY: -50, deltaMode: 0, ctrlKey: true, preventDefault() { this.prevented = true; }}, extra); },
        flush() { let count = 0; while (frames.size) { assert.ok(++count < 100); const [id, callback] = frames.entries().next().value; frames.delete(id); callback(); } }
    };
}

test("trackpad pinch smoothly zooms at the pointer, clamps limits and preserves page scrolling", () => {
    const env = trackpad();
    const scroll = env.event({ctrlKey: false});
    env.events.wheel(scroll);
    assert.equal(scroll.prevented, undefined);
    assert.equal(env.frames.size, 0);
    const pinch = env.event({});
    env.events.wheel(pinch);
    assert.equal(pinch.prevented, true);
    env.events.wheel(env.event({}));
    assert.equal(env.frames.size, 1);
    env.flush();
    assert.equal(env.map.getZoom(), 2);
    assert.ok(env.changes.length > 1);
    assert.deepEqual(env.changes[0].point, [140, 120]);
    for (const [deltaY, expected] of [[-10000, 6], [10000, -1]]) {
        env.events.wheel(env.event({deltaY})); env.flush();
        assert.equal(env.map.getZoom(), expected);
    }
    env.events.wheel(env.event({}));
    env.destroy();
    assert.equal(env.frames.size, 0);
    assert.deepEqual(env.events, {});
});

test("Safari gesture scale doubles map size without also applying Ctrl+wheel", () => {
    const env = trackpad();
    const start = env.event({});
    env.events.gesturestart(start);
    assert.equal(start.prevented, true);
    env.events.gesturechange(env.event({scale: 2}));
    env.events.wheel(env.event({deltaY: -100}));
    env.flush();
    assert.equal(env.map.getZoom(), 2);
    env.events.gestureend(env.event({}));
    env.events.wheel(env.event({deltaY: 100})); env.flush();
    assert.equal(env.map.getZoom(), 1);
    env.destroy();
});

test("titles use textContent, links use current tab, previews must be local", () => {
    const doc = {createElement: node};
    const title = '<img src=x onerror="alert(1)">';
    const link = api.markerElement(doc, {title, url: "/world/ice/", preview: "/map/previews/1/", color: "#123456"}, false, null, "https://subpolare.ru");
    assert.equal(link.tag, "a");
    assert.equal(link.target, "_self");
    assert.equal(link.attributes["aria-label"], title);
    assert.equal(link.children[1].textContent, title);
    assert.equal(link.children[1].innerHTML, undefined);
    assert.equal(link.children[0].src, "https://subpolare.ru/map/previews/1/");
    link.children[0].events.error();
    assert.equal(link.children[0].removed, true);
    const bad = api.markerElement(doc, {title, url: "javascript:alert(1)", preview: "https://evil.test/cover.jpg", color: "red"}, true, null, "https://subpolare.ru");
    assert.equal(bad.href, "#");
    assert.equal(bad.children[0].src, undefined);
    assert.equal(bad.style["--marker-color"], "#333333");
    for (const url of ["//evil.test", "javascript:alert(1)", "data:text/html,x", "/\\evil.test", "https://u:p@evil.test", "https://x\n.test"]) assert.equal(api.safeURL(url, "https://subpolare.ru"), null);
});

function environment({mountError = false, deferredMount = false, observer = true, resourceError = false} = {}) {
    const events = {};
    const fallback = node("div");
    const shell = {querySelector: selector => selector === ".map-fallback" ? fallback : null};
    const element = Object.assign(node("div"), {
        dataset: {mode: "public", library: "leaflet.js", libraryCss: "leaflet.css", css: "map.css", code: "map.js"},
        isConnected: true, closest: () => shell,
        getBoundingClientRect: () => ({top: 2000, bottom: 2560})
    });
    const observers = [];
    let mounts = 0, destroys = 0, signal, finishMount;
    const resources = [];
    const doc = {
        createElement: node,
        querySelectorAll: () => element.isConnected ? [element] : [],
        addEventListener(name, callback) { events[name] = callback; },
        head: {appendChild(child) { resources.push(child); queueMicrotask(() => resourceError ? child.onerror() : child.onload()); }}
    };
    const win = {
        setTimeout, clearTimeout, AbortController, innerHeight: 800,
        addEventListener(name, callback) { events[name] = callback; },
        removeEventListener(name) { delete events[name]; },
        ArticleMap: {async mount(el, controllerSignal) {
            mounts++;
            signal = controllerSignal;
            if (mountError) throw new Error("unavailable");
            if (deferredMount) await new Promise(resolve => { finishMount = resolve; });
            return {destroy() { destroys++; }};
        }}
    };
    if (observer) win.IntersectionObserver = class {
        constructor(callback, options) { this.callback = callback; this.options = options; observers.push(this); }
        observe(el) { this.element = el; }
        disconnect() { this.disconnected = true; }
    };
    const instance = loader(win, doc);
    return {instance, events, element, observers, resources, fallback,
        enter() { observers[0].callback([{isIntersecting: true}]); },
        finish() { finishMount(); },
        get mounts() { return mounts; }, get destroys() { return destroys; }, get signal() { return signal; }};
}
const tick = () => new Promise(resolve => setImmediate(resolve));

test("lazy load makes no resource requests before 300px threshold and initializes once", async () => {
    const env = environment();
    assert.equal(env.resources.length, 0);
    assert.equal(env.observers[0].options.rootMargin, "300px");
    env.instance.scan();
    assert.equal(env.observers.length, 1);
    env.enter();
    env.enter();
    await tick();
    assert.equal(env.mounts, 1);
    assert.equal(env.fallback.hidden, true);
    assert.equal(env.observers[0].disconnected, true);
    env.events["htmx:load"]();
    assert.equal(env.mounts, 1);
    env.instance.destroy(env.element);
});

test("HTMX cleanup destroys map, aborts work and allows a fresh restored map", async () => {
    const env = environment();
    env.enter();
    await tick();
    env.events["htmx:beforeCleanupElement"]({detail: {elt: {contains: () => true}}});
    assert.equal(env.destroys, 1);
    assert.equal(env.signal.aborted, true);
    assert.equal(env.fallback.hidden, false);
    env.events["htmx:historyRestore"]();
    env.observers[1].callback([{isIntersecting: true}]);
    await tick();
    assert.equal(env.mounts, 2);
    env.events["htmx:beforeHistorySave"]();
    assert.equal(env.destroys, 2);
});

test("removal while mount is pending disposes the late map", async () => {
    const env = environment({deferredMount: true});
    env.enter();
    await tick();
    env.instance.destroy(env.element);
    env.finish();
    await tick();
    assert.equal(env.destroys, 1);
    assert.equal(env.fallback.hidden, false);
});

test("data failures preserve fallback and do not retry repeatedly", async () => {
    const env = environment({mountError: true});
    env.enter();
    await tick();
    assert.equal(env.fallback.hidden, false);
    env.instance.scan();
    assert.equal(env.mounts, 1);
});

test("library or CSS loading failure leaves the article list usable", async () => {
    const env = environment({resourceError: true});
    env.enter();
    await tick();
    assert.equal(env.fallback.hidden, false);
    assert.equal(env.mounts, 0);
    assert.ok(env.resources.every(resource => resource.removed));
});

test("without IntersectionObserver, scroll fallback still defers loading", async () => {
    const env = environment({observer: false});
    assert.equal(env.resources.length, 0);
    env.element.getBoundingClientRect = () => ({top: 1000, bottom: 1560});
    env.events.scroll();
    await tick();
    assert.equal(env.mounts, 1);
    assert.equal(env.events.scroll, undefined);
    env.instance.destroy(env.element);
});
