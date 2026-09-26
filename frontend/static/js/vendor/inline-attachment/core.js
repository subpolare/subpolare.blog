// Adapted from vas3k/vas3k.club 2c8bb71126336106d46823144046837defc27960; see LICENSE.
// Plain scripts; per-file placeholders, range edits, validation and timeout hooks for the blog.
/**
 * Default configuration options
 *
 * @type {Object}
 **/
const DEFAULT_SETTINGS = {
    /**
     * URL where the file will be sent
     */
    uploadUrl: "upload_attachment.php",

    /**
     * Which method will be used to send the file to the upload URL
     */
    uploadMethod: "POST",

    /**
     * Name in which the file will be placed
     */
    uploadFieldName: "file",

    /**
     * Extension which will be used when a file extension could not
     * be detected
     */
    defaultExtension: "png",

    /**
     * JSON field which refers to the uploaded file URL
     */
    jsonFieldName: "filename",

    /**
     * Allowed MIME types
     */
    allowedTypes: [
        "image/jpeg", "image/png", "image/jpg", "image/gif", "image/webp", "image/avif",
        "video/mp4", "video/webm", "video/quicktime",
    ],

    /**
     * Text which will be inserted when dropping or pasting a file.
     * Acts as a placeholder which will be replaced when the file is done with uploading
     */
    progressText: "![Uploading file...]()",

    /**
     * When a file has successfully been uploaded the progressText
     * will be replaced by the urlText, the {filename} tag will be replaced
     * by the filename that has been returned by the server
     */
    urlText: "![file]({filename})",
    filenameTag: "{filename}",

    /**
     * Text which will be used when uploading has failed
     */
    errorText: "Error uploading file",

    /**
     * Extra parameters which will be send when uploading a file
     */
    extraParams: {},

    /**
     * Extra headers which will be send when uploading a file
     */
    extraHeaders: {},

    /**
     * Before the file is send
     */
    beforeFileUpload: function () {
        return true;
    },

    /**
     * Triggers when a file is dropped or pasted
     */
    onFileReceived: function () {},
    onFileRejected: function () {},

    /**
     * Custom upload handler
     *
     * @return {Boolean} when false is returned it will prevent default upload behavior
     */
    onFileUploadResponse: function () {
        return true;
    },

    /**
     * Custom error handler. Runs after removing the placeholder text and before the alert().
     * Return false from this function to prevent the alert dialog.
     *
     * @return {Boolean} when false is returned it will prevent default error behavior
     */
    onFileUploadError: function () {
        return true;
    },

    /**
     * When a file has successfully been uploaded
     */
    onFileUploaded: function () {},
};

/**
 * Initializes settings object
 * @param {Object} settings Custom settings
 * @returns {{settings}} Initialized settings
 */
function initSettings(settings) {
    return {...DEFAULT_SETTINGS, ...settings}
}

/**
 * Uploads the blob
 *
 * @param  {Blob} file blob data received from event.dataTransfer object
 * @param {Object} settings for inline attachment
 * @param {(XMLHttpRequest) => {}} onSuccess upload handler
 * @param {(XMLHttpRequest) => {}} onFailure upload handler
 * @return {XMLHttpRequest} request object which sends the file
 */
function uploadFile(file, settings, onSuccess = () => {}, onFailure = () => {}) {
    let formData = new FormData(),
        xhr = new XMLHttpRequest(),
        extension = settings.defaultExtension;

    if (typeof settings.setupFormData === "function") {
        settings.setupFormData(formData, file);
    }

    // Attach the file. If coming from clipboard, add a default filename (only works in Chrome for now)
    // http://stackoverflow.com/questions/6664967/how-to-give-a-blob-uploaded-as-formdata-a-file-name
    if (file.name) {
        const fileNameMatches = file.name.match(/\.(.+)$/);
        if (fileNameMatches) {
            extension = fileNameMatches[1];
        }
    }

    let remoteFilename = "image-" + Date.now() + "." + extension;
    if (typeof settings.remoteFilename === "function") {
        remoteFilename = settings.remoteFilename(file);
    }

    formData.append(settings.uploadFieldName, file, remoteFilename);

    // Append the extra parameters to the formdata
    if (typeof settings.extraParams === "object") {
        for (let key in settings.extraParams) {
            if (settings.extraParams.hasOwnProperty(key)) {
                formData.append(key, settings.extraParams[key]);
            }
        }
    }

    xhr.open("POST", settings.uploadUrl);

    // Add any available extra headers
    if (typeof settings.extraHeaders === "object") {
        for (let header in settings.extraHeaders) {
            if (settings.extraHeaders.hasOwnProperty(header)) {
                xhr.setRequestHeader(header, settings.extraHeaders[header]);
            }
        }
    }

    xhr.onload = function () {
        // If HTTP status is OK or Created
        if (xhr.status === 200 || xhr.status === 201) {
            onSuccess(xhr);
        } else {
            onFailure(xhr);
        }
    };

    xhr.timeout = 90000;
    xhr.ontimeout = xhr.onabort = function () { onFailure(xhr); };
    xhr.upload.onprogress = settings.onUploadProgress || function () {};

    xhr.onerror = function () {
        onFailure(xhr);
    };

    if (settings.beforeFileUpload(xhr) !== false) {
        xhr.send(formData);
    }
    return xhr;
}

    /**
     * Returns if the given file is allowed to handle
     *
     * @param {Blob} file
     * @param {Object} settings
     */
function isFileAllowed(file, settings) {
    if (file.kind === "string") {
        return false;
    }
    if (settings.allowedTypes.indexOf("*") === 0) {
        return true;
    } else {
        return settings.allowedTypes.indexOf(file.type) >= 0;
    }
};


/*jslint newcap: true */
/*global XMLHttpRequest: false, FormData: false */
/*
 * Inline Text Attachment
 *
 * Author: Roy van Kaathoven
 * Contact: ik@royvankaathoven.nl
 */
(function (document, window) {
    "use strict";

    var inlineAttachment = function (options, instance) {
        this.settings = initSettings(options);
        this.editor = instance;
        this.lastValue = null;
    };

    /**
     * Will holds the available editors
     *
     * @type {Object}
     */
    inlineAttachment.editors = {};

    /**
     * Utility functions
     */
    inlineAttachment.util = {
        /**
         * Append a line of text at the bottom, ensuring there aren't unnecessary newlines
         *
         * @param {String} appended Current content
         * @param {String} previous Value which should be appended after the current content
         */
        appendInItsOwnLine: function (previous, appended) {
            return (previous + "\n\n[[D]]" + appended).replace(/(\n{2,})\[\[D\]\]/, "\n\n").replace(/^(\n*)/, "");
        },

        /**
         * Inserts the given value at the current cursor position of the textarea element
         *
         * @param  {HtmlElement} el
         * @param  {String} value Text which will be inserted at the cursor position
         */
        insertTextAtCursor: function (el, text) {
            var scrollPos = el.scrollTop,
                strPos = 0,
                browser = false,
                range;

            if (el.selectionStart || el.selectionStart === "0") {
                browser = "ff";
            } else if (document.selection) {
                browser = "ie";
            }

            if (browser === "ie") {
                el.focus();
                range = document.selection.createRange();
                range.moveStart("character", -el.value.length);
                strPos = range.text.length;
            } else if (browser === "ff") {
                strPos = el.selectionStart;
            }

            var front = el.value.substring(0, strPos);
            var back = el.value.substring(strPos, el.value.length);
            el.value = front + text + back;
            strPos = strPos + text.length;
            if (browser === "ie") {
                el.focus();
                range = document.selection.createRange();
                range.moveStart("character", -el.value.length);
                range.moveStart("character", strPos);
                range.moveEnd("character", 0);
                range.select();
            } else if (browser === "ff") {
                el.selectionStart = strPos;
                el.selectionEnd = strPos;
                el.focus();
            }
            el.scrollTop = scrollPos;
        },
    };

    /**
     * Handles upload response
     *
     * @param  {XMLHttpRequest} xhr
     * @return {Void}
     */
    inlineAttachment.prototype.onFileUploadResponse = function (xhr) {
        if (this.settings.onFileUploadResponse.call(this, xhr) !== false) {
            var result;
            try { result = JSON.parse(xhr.responseText); }
            catch (error) { this.onFileUploadError(xhr); return; }
            var
                filename = result && result[this.settings.jsonFieldName];

            if (result && typeof filename === "string" && /^https?:\/\//.test(filename)) {
                var newValue;
                if (typeof this.settings.urlText === "function") {
                    newValue = this.settings.urlText.call(this, filename, result);
                } else {
                    newValue = this.settings.urlText.replace(this.settings.filenameTag, filename);
                }
                this.editor.replaceValue(this.lastValue, newValue);
                this.settings.onFileUploaded.call(this, filename);
            } else { this.onFileUploadError(xhr); }
        }
    };

    /**
     * Called when a file has failed to upload
     *
     * @param  {XMLHttpRequest} xhr
     * @return {Void}
     */
    inlineAttachment.prototype.onFileUploadError = function (xhr) {
        if (this.settings.onFileUploadError.call(this, xhr) !== false) {
            this.editor.replaceValue(this.lastValue, this.lastValue.replace("Загружаю файл", "Ошибка загрузки файла"));
        }
    };

    /**
     * Called when a file has been inserted, either by drop or paste
     *
     * @param  {File} file
     * @return {Void}
     */
    inlineAttachment.prototype.onFileInserted = function (file) {
        if (this.settings.onFileReceived.call(this, file) !== false) {
            this.lastValue = this.settings.progressText.replace("...", "... " + (++inlineAttachment.uploadCounter));
            this.editor.insertValue(this.lastValue);
            return true;
        }
        return false;
    };

    /**
     * Called when a paste event occured
     * @param  {Event} e
     * @return {Boolean} if the event was handled
     */
    // One context per file: concurrent uploads must not share lastValue.
    inlineAttachment.uploadCounter = 0;
    inlineAttachment.prototype.upload = function (file) {
        if (!file || !isFileAllowed(file, this.settings)) {
            this.settings.onFileRejected(file);
            return;
        }
        const attachment = new inlineAttachment(this.settings, this.editor);
        if (!attachment.onFileInserted(file)) return;
        uploadFile(file, attachment.settings,
            attachment.onFileUploadResponse.bind(attachment),
            attachment.onFileUploadError.bind(attachment));
    };
    inlineAttachment.prototype.onPaste = function (event) {
        const data = event.clipboardData;
        if (!data) return false;
        const files = data.items ? Array.from(data.items).filter(item => item.kind === "file")
            .map(item => item.getAsFile()) : Array.from(data.files || []);
        if (!files.length) return false;
        event.preventDefault();
        files.forEach(file => this.upload(file));
        return true;
    };
    inlineAttachment.prototype.onDrop = function (event) {
        const files = Array.from(event.dataTransfer.files || []);
        if (!files.length) return false;
        files.forEach(file => this.upload(file));
        return true;
    };
    inlineAttachment.prototype.onFileInputUpload = function (event) {
        Array.from(event.target.files).forEach(file => this.upload(file));
        event.target.value = "";
        return true;
    };

    window.inlineAttachment = inlineAttachment;
})(document, window);
