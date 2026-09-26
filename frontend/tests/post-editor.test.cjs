const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {runInNewContext} = require('node:vm');
const {join} = require('node:path');

function setup() {
    const requests = [];
    const events = {};
    const fileInput = {addEventListener: (name, callback) => events[name] = callback};
    const cm = {
        text: 'Selected text must survive.',
        cursor: 'Selected text must survive.'.length,
        getValue() { return this.text; },
        getCursor() { return this.cursor; },
        posFromIndex(index) { return index; },
        replaceRange(value, from, to = from) {
            this.text = this.text.slice(0, from) + value + this.text.slice(to);
            this.cursor = from + value.length;
        },
        getWrapperElement() { return {addEventListener: (name, callback) => events[name] = callback}; },
        on(name, callback) { events[name] = callback; },
    };
    const context = {
        document: {}, window: {},
        FormData: class {
            values = {};
            append(name, value) { this.values[name] = value; }
        },
        XMLHttpRequest: class {
            headers = {};
            upload = {};
            constructor() { requests.push(this); }
            open(method, url) { this.method = method; this.url = url; }
            setRequestHeader(name, value) { this.headers[name] = value; }
            send(data) { this.data = data; }
            finish(body, status = 200) { this.status = status; this.responseText = body; this.onload(); }
        },
    };
    const vendor = join(__dirname, '../static/js/vendor/inline-attachment');
    runInNewContext(readFileSync(join(vendor, 'core.js'), 'utf8'), context);
    context.inlineAttachment = context.window.inlineAttachment;
    runInNewContext(readFileSync(join(vendor, 'codemirror4.js'), 'utf8'), context);
    let pending = 0;
    let rejected = 0;
    context.inlineAttachment.editors.codemirror4.attach(cm, {
        fileInputEl: fileInput,
        uploadUrl: '/editor/upload/', uploadFieldName: 'media', jsonFieldName: 'uploaded',
        extraHeaders: {Accept: 'application/json', 'X-CSRFToken': 'test-csrf'},
        allowedTypes: ['image/png'], progressText: '![Загружаю файл...]()', urlText: '![]({filename})',
        onFileReceived() { pending++; },
        onFileUploaded() { pending--; },
        onFileUploadError() { pending--; },
        onFileRejected() { rejected++; },
    });
    return {cm, events, requests, get pending() { return pending; }, get rejected() { return rejected; }};
}

const png = {name: 'test.png', type: 'image/png', size: 12};

test('concurrent uploads replace only their own markers and preserve text typed in between', () => {
    const s = setup();
    const event = {target: {files: [png, png], value: 'file'}, stopPropagation() {}, preventDefault() {}};
    s.events.change(event);
    assert.equal(s.pending, 2);
    assert.equal(event.target.value, '');
    s.cm.text += '\nKeep typing';
    s.requests[1].finish(JSON.stringify({uploaded: 'https://media.example.test/second.png'}));
    s.requests[0].finish(JSON.stringify({uploaded: 'https://media.example.test/first.png'}));
    assert.equal(s.cm.text, 'Selected text must survive.![](https://media.example.test/first.png)![](https://media.example.test/second.png)\nKeep typing');
    assert.equal(s.pending, 0);
    assert.equal(s.requests[0].data.values.media, png);
    assert.equal(s.requests[0].headers.Accept, 'application/json');
    assert.equal(s.requests[0].headers['X-CSRFToken'], 'test-csrf');
    assert.equal(s.requests[0].data.values.code, undefined);
});

test('paste and drop upload images, while plain text paste is left to CodeMirror', () => {
    const s = setup();
    let prevented = 0;
    s.events.paste({clipboardData: {items: [{kind: 'string'}]}, preventDefault() { prevented++; }});
    assert.equal(prevented, 0);
    s.events.paste({clipboardData: {items: [{kind: 'file', getAsFile: () => png}]}, preventDefault() { prevented++; }});
    s.events.drop(s.cm, {dataTransfer: {files: [png]}, stopPropagation() {}, preventDefault() { prevented++; }});
    assert.equal(prevented, 2);
    assert.equal(s.requests.length, 2);
});

test('unsupported dropped files are consumed with an explicit rejection', () => {
    const s = setup();
    let prevented = false;
    s.events.drop(s.cm, {dataTransfer: {files: [{type: 'text/html'}]}, stopPropagation() {}, preventDefault() { prevented = true; }});
    assert.equal(prevented, true);
    assert.equal(s.rejected, 1);
    assert.equal(s.requests.length, 0);
});

test('invalid JSON, missing URL, HTTP failures and timeouts leave a visible failed marker', () => {
    for (const result of ['null', '{}', 'not JSON', '{"uploaded":"javascript:bad"}', 'http-error', 'timeout', 'abort', 'network']) {
        const s = setup();
        s.events.change({target: {files: [png]}, stopPropagation() {}, preventDefault() {}});
        const xhr = s.requests[0];
        if (result === 'timeout') xhr.ontimeout();
        else if (result === 'abort') xhr.onabort();
        else if (result === 'network') xhr.onerror();
        else xhr.finish(result, result === 'http-error' ? 503 : 200);
        assert.equal(s.pending, 0, result);
        assert.match(s.cm.text, /Ошибка загрузки файла/, result);
        assert.ok(s.cm.text.startsWith('Selected text must survive.'), result);
    }
});

test('a deliberately deleted placeholder is not reinserted by a late upload response', () => {
    const s = setup();
    s.events.change({target: {files: [png]}, stopPropagation() {}, preventDefault() {}});
    s.cm.text = 'User removed the placeholder.';
    s.requests[0].finish(JSON.stringify({uploaded: 'https://media.example.test/late.png'}));
    assert.equal(s.cm.text, 'User removed the placeholder.');
    assert.equal(s.pending, 0);
});
