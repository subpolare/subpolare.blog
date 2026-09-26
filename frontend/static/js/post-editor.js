(function () {
    function copyText(value) {
        if (navigator.clipboard && window.isSecureContext) {
            return navigator.clipboard.writeText(value);
        }

        const element = document.createElement("textarea");

        element.value = value;
        element.setAttribute("readonly", "");
        element.style.position = "fixed";
        element.style.left = "-9999px";

        document.body.appendChild(element);
        element.select();
        document.execCommand("copy");
        document.body.removeChild(element);

        return Promise.resolve();
    }

    function attachCopyButton(editor) {
        const button = document.getElementById("post-editor-copy");

        if (!button) {
            return;
        }

        const initialText = button.innerText;

        button.addEventListener("click", function () {
            copyText(editor.value()).then(function () {
                button.innerText = "Скопировано";
                setTimeout(function () {
                    button.innerText = initialText;
                }, 1200);
            });
        });
    }

    function attachSaveShortcut(form) {
        document.addEventListener("keydown", function (event) {
            const isSave = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s";

            if (!isSave) {
                return;
            }

            event.preventDefault();

            if (form.requestSubmit) {
                form.requestSubmit();
            } else {
                form.querySelector('[type="submit"]').click();
            }
        });
    }

    function attachImagePreview() {
        const input = document.getElementById("id_image");
        const preview = document.getElementById("post-image-preview");

        if (!input || !preview) {
            return;
        }

        const image = preview.querySelector("img");

        function updatePreview() {
            const value = input.value.trim();

            if (!value) {
                preview.hidden = true;
                image.removeAttribute("src");
                return;
            }

            image.src = value;
            preview.hidden = false;
        }

        input.addEventListener("input", updatePreview);
        updatePreview();
    }

    document.addEventListener("DOMContentLoaded", function () {
        const textarea = document.getElementById("post-editor");

        if (!textarea || !window.EasyMDE) {
            return;
        }

        const form = textarea.closest("form");
        const csrfToken = form.querySelector('[name="csrfmiddlewaretoken"]').value;
        const status = document.getElementById("post-editor-status");
        const submitButton = form.querySelector('[type="submit"]');
        const fileInput = document.createElement("input");
        fileInput.type = "file";
        fileInput.name = "attach-image";
        fileInput.multiple = true;
        const allowedTypes = ["image/jpeg", "image/png", "image/webp", "image/jpg", "image/gif"];
        fileInput.accept = allowedTypes.join();
        let uploads = 0;
        let uploadError = "";
        const unfinishedUpload = /!\[(?:Загружаю файл|Ошибка загрузки файла)\.\.\. \d+\]\(\)/;

        // Each EasyMDE preview pane owns its request: stale responses cannot replace new text.
        const previews = new WeakMap();
        function previewRender(text, pane) {
            const previous = previews.get(pane);
            if (previous && previous.text === text && !previous.failed) return null;
            if (previous) {
                clearTimeout(previous.timer);
                previous.controller.abort();
            }
            const state = {controller: new AbortController(), text: text};
            previews.set(pane, state);
            state.timer = setTimeout(async function () {
                const timeout = setTimeout(() => state.controller.abort(), 15000);
                try {
                    const response = await fetch(form.dataset.previewUrl, {
                        method: "POST",
                        credentials: "same-origin",
                        headers: {"X-CSRFToken": csrfToken, "Accept": "application/json"},
                        body: new URLSearchParams({text}),
                        signal: state.controller.signal
                    });
                    if (!response.ok) throw new Error("Preview failed");
                    const result = await response.json();
                    if (previews.get(pane) !== state) return;
                    const frame = document.createElement("iframe");
                    frame.className = "post-editor-preview-frame";
                    frame.title = "Предпросмотр поста";
                    // Keep local fonts/styles working, but never execute raw post scripts/forms.
                    // Only this parent page binds the blog's read-only preview interactions.
                    frame.setAttribute("sandbox", "allow-same-origin");
                    frame.addEventListener("load", function () {
                        const document = frame.contentDocument;
                        if (!document) return;
                        document.documentElement.setAttribute("theme", window.document.documentElement.getAttribute("theme") || "light");
                        document.querySelectorAll(".block-spoiler").forEach(function (spoiler) {
                            spoiler.addEventListener("click", function () {
                                spoiler.querySelector(".block-spoiler-button")?.classList.toggle("block-spoiler-button-hidden");
                                spoiler.querySelector(".block-spoiler-text")?.classList.toggle("block-spoiler-text-visible");
                            });
                        });
                        document.querySelectorAll("pre code").forEach(code => window.hljs?.highlightBlock(code));
                        document.addEventListener("click", function (event) {
                            const link = event.target.closest("a");
                            if (link && !link.getAttribute("href")?.startsWith("#")) event.preventDefault();
                        });
                    });
                    frame.srcdoc = result.html;
                    pane.replaceChildren(frame);
                } catch (error) {
                    if (previews.get(pane) === state) {
                        state.failed = true;
                        pane.textContent = "Не удалось загрузить предпросмотр. Откройте его ещё раз. Текст сохранён в редакторе.";
                    }
                } finally {
                    clearTimeout(timeout);
                }
            }, 300);
            return "Загружаю предпросмотр…";
        }

        // EasyMDE defaults and the basic toolbar follow the Club's markdown-editor.js / App.js.
        const editor = new EasyMDE({
            element: textarea,
            autoDownloadFontAwesome: false,
            previewImagesInEditor: true,
            spellChecker: false,
            forceSync: true,
            status: false,
            tabSize: 4,
            previewRender: previewRender,
            lineWrapping: true,
            autofocus: true,
            blockStyles: {
                bold: "**",
                italic: "_"
            },
            autosave: {
                enabled: false
            },
            toolbar: [
                {
                    name: "bold",
                    action: EasyMDE.toggleBold,
                    className: "fa fa-bold",
                    title: "Жирный"
                },
                {
                    name: "italic",
                    action: EasyMDE.toggleItalic,
                    className: "fa fa-italic",
                    title: "Курсив"
                },
                {
                    name: "heading",
                    action: EasyMDE.toggleHeadingSmaller,
                    className: "fa fa-heading",
                    title: "Заголовок"
                },
                {
                    name: "quote",
                    action: EasyMDE.toggleBlockquote,
                    className: "fa fa-quote-right",
                    title: "Цитата"
                },
                "|",
                {
                    name: "unordered-list",
                    action: EasyMDE.toggleUnorderedList,
                    className: "fa fa-list-ul",
                    title: "Список"
                },
                {
                    name: "ordered-list",
                    action: EasyMDE.toggleOrderedList,
                    className: "fa fa-list-ol",
                    title: "Нумерованный список"
                },
                "|",
                {
                    name: "link",
                    action: EasyMDE.drawLink,
                    className: "fa fa-link",
                    title: "Ссылка"
                },
                {
                    name: "image",
                    action: EasyMDE.drawImage,
                    className: "fa fa-image",
                    title: "Картинка"
                },
                {
                    name: "upload-file",
                    action: () => fileInput.click(),
                    className: "fa fa-paperclip",
                    title: "Загрузить изображение"
                },
                {
                    name: "code",
                    action: EasyMDE.toggleCodeBlock,
                    className: "fa fa-code",
                    title: "Код"
                },
                "|",
                {
                    name: "preview",
                    action: EasyMDE.togglePreview,
                    className: "fa fa-eye no-disable",
                    title: "Предпросмотр"
                },
                {
                    name: "side-by-side",
                    action: EasyMDE.toggleSideBySide,
                    className: "fa fa-columns no-disable no-mobile",
                    title: "Редактор и предпросмотр"
                },
                {
                    name: "fullscreen",
                    action: EasyMDE.toggleFullScreen,
                    className: "fa fa-arrows-alt no-disable no-mobile",
                    title: "На весь экран"
                }
            ]
        });

        editor.codemirror.addKeyMap({
            Home: "goLineLeft",
            End: "goLineRight"
        });

        function updateUploadStatus() {
            submitButton.disabled = uploads > 0;
            if (uploads) {
                status.textContent = "Загружаю файлов: " + uploads + ". Дождитесь ответа хранилища.";
            } else if (unfinishedUpload.test(editor.value())) {
                status.textContent = (uploadError || "Есть незавершённые загрузки.") + " Повторите загрузку и удалите её старую отметку из текста.";
            } else {
                uploadError = "";
                status.textContent = "";
            }
        }

        inlineAttachment.editors.codemirror4.attach(editor.codemirror, {
            fileInputEl: fileInput,
            uploadUrl: form.dataset.uploadUrl,
            uploadMethod: "POST",
            uploadFieldName: "media",
            jsonFieldName: "uploaded",
            progressText: "![Загружаю файл...]()",
            urlText: "![]({filename})",
            allowedTypes: allowedTypes,
            extraHeaders: {Accept: "application/json", "X-CSRFToken": csrfToken},
            onFileReceived: function (file) {
                if (!file.size || file.size > 14 * 1024 * 1024) {
                    status.textContent = "Нужен непустой файл размером до 14 МБ.";
                    return false;
                }
                uploads++;
                updateUploadStatus();
            },
            onFileRejected: function () {
                status.textContent = "Выберите изображение JPEG, PNG, WebP или GIF.";
            },
            onUploadProgress: function (event) {
                if (event.lengthComputable) {
                    status.textContent = "Загружаю файлов: " + uploads + ". Передано " + Math.round(event.loaded / event.total * 100) + "% текущего файла. Ожидаю хранилище…";
                }
            },
            onFileUploaded: function () {
                uploads--;
                updateUploadStatus();
            },
            onFileUploadError: function (xhr) {
                try {
                    uploadError = JSON.parse(xhr.responseText).error || "Не удалось загрузить файл.";
                } catch (error) {
                    uploadError = "Не удалось загрузить файл. Проверьте соединение.";
                }
                uploads--;
                updateUploadStatus();
                return true;
            }
        });

        editor.codemirror.on("change", updateUploadStatus);
        form.addEventListener("submit", function (event) {
            if (uploads || unfinishedUpload.test(editor.value())) {
                event.preventDefault();
                updateUploadStatus();
            }
        });
        window.addEventListener("beforeunload", function (event) {
            if (uploads) {
                event.preventDefault();
                event.returnValue = "";
            }
        });

        attachCopyButton(editor);
        attachSaveShortcut(form);
        attachImagePreview();

        setTimeout(function () {
            editor.codemirror.refresh();
        }, 50);
    });
})();
