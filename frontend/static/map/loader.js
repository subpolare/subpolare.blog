(function (root, factory) {
    if (typeof module === "object" && module.exports) module.exports = factory;
    else if (root.ArticleMapLoader) root.ArticleMapLoader.scan();
    else root.ArticleMapLoader = factory(root, root.document);
})(typeof window === "undefined" ? globalThis : window, function (win, doc) {
    "use strict";
    const states = new Map();
    let assets;

    function resource(tag, url) {
        return new Promise(function (resolve, reject) {
            const node = doc.createElement(tag);
            const timer = win.setTimeout(failed, 12000);
            function failed() {
                win.clearTimeout(timer);
                node.remove();
                reject(new Error("Map resource unavailable"));
            }
            node.onload = function () { win.clearTimeout(timer); resolve(); };
            node.onerror = failed;
            if (tag === "script") node.src = url;
            else { node.rel = "stylesheet"; node.href = url; }
            doc.head.appendChild(node);
        });
    }

    function loadAssets(element) {
        if (!assets) {
            const data = element.dataset;
            assets = Promise.all([
                win.L ? Promise.resolve() : resource("script", data.library),
                resource("link", data.libraryCss), resource("link", data.css),
                win.ArticleMap ? Promise.resolve() : resource("script", data.code)
            ]).catch(function (error) { assets = null; throw error; });
        }
        return assets;
    }

    function fallback(element, visible) {
        const shell = element.closest("[data-map-shell]");
        const list = shell.querySelector(".map-fallback");
        const error = shell.querySelector(".map-load-error");
        if (list) list.hidden = !visible;
        if (error) error.hidden = !visible;
    }

    function destroy(element) {
        const state = states.get(element);
        if (!state) return;
        states.delete(element);
        if (state.stopObserving) state.stopObserving();
        if (state.controller) state.controller.destroy();
        if (state.abort) state.abort.abort();
        element.replaceChildren();
        fallback(element, true);
    }

    async function start(element, state) {
        if (state.started) return;
        state.started = true;
        if (state.stopObserving) state.stopObserving();
        try {
            await loadAssets(element);
            if (states.get(element) !== state || !element.isConnected) return;
            state.abort = new win.AbortController();
            state.controller = await win.ArticleMap.mount(element, state.abort.signal);
            if (states.get(element) !== state || !element.isConnected) {
                state.controller.destroy();
                return;
            }
            fallback(element, false);
        } catch (error) {
            if (states.get(element) === state) {
                destroy(element);
                // Keep failure stable until a fresh HTMX visit, without a retry loop.
                states.set(element, {started: true});
            }
        }
    }

    function scan() {
        states.forEach(function (state, element) { if (!element.isConnected) destroy(element); });
        doc.querySelectorAll("[data-article-map]").forEach(function (element) {
            if (states.has(element)) return;
            const state = {};
            states.set(element, state);
            if (element.dataset.mode !== "public") { start(element, state); return; }
            if (win.IntersectionObserver) {
                const observer = new win.IntersectionObserver(function (entries) {
                    if (entries.some(entry => entry.isIntersecting)) start(element, state);
                }, {rootMargin: "300px"});
                state.stopObserving = function () { observer.disconnect(); };
                observer.observe(element);
            } else {
                const check = function () {
                    const rect = element.getBoundingClientRect();
                    if (rect.top <= win.innerHeight + 300 && rect.bottom >= -300) start(element, state);
                };
                win.addEventListener("scroll", check, {passive: true});
                win.addEventListener("resize", check);
                state.stopObserving = function () {
                    win.removeEventListener("scroll", check);
                    win.removeEventListener("resize", check);
                };
                check();
            }
        });
    }

    doc.addEventListener("htmx:beforeCleanupElement", function (event) {
        const removed = event.detail.elt;
        states.forEach(function (state, element) {
            if (removed === element || removed.contains(element)) destroy(element);
        });
    });
    doc.addEventListener("htmx:beforeHistorySave", function () {
        Array.from(states.keys()).forEach(destroy);
    });
    ["DOMContentLoaded", "htmx:load", "htmx:afterSwap", "htmx:historyRestore"].forEach(function (name) {
        doc.addEventListener(name, scan);
    });
    win.addEventListener("pageshow", scan);
    scan();
    return {scan: scan, destroy: destroy};
});
