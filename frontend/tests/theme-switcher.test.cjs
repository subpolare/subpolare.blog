const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

test("theme button toggles from its icon, persists choice and stays in sync after HTMX navigation", () => {
    let theme, saved = "dark", pressed;
    const events = {};
    const context = vm.createContext({
        document: {
            documentElement: {getAttribute: () => theme, setAttribute: (_, value) => { theme = value; }},
            querySelectorAll: () => [{setAttribute: (_, value) => { pressed = value; }}],
            addEventListener: (name, handler) => { events[name] = handler; }
        },
        window: {matchMedia: () => ({matches: false}), addEventListener() {}},
        localStorage: {getItem: () => saved, setItem: (_, value) => { saved = value; }}
    });
    for (const file of ["main.js", "theme-switcher.js"]) {
        vm.runInContext(fs.readFileSync(path.join(__dirname, "../static/js", file), "utf8"), context);
    }
    events.DOMContentLoaded();
    assert.equal(theme, "dark");
    assert.equal(pressed, "true");
    context.toggleTheme({target: {tagName: "SPAN"}});
    assert.equal(theme, "light");
    assert.equal(saved, "light");
    assert.equal(pressed, "false");
    events["htmx:load"]();
    assert.equal(pressed, "false");
    context.toggleTheme({target: {tagName: "BUTTON"}});
    assert.equal(theme, "dark");
    assert.equal(saved, "dark");
    assert.equal(pressed, "true");
});
