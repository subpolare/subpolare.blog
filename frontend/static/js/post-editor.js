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
                form.submit();
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

        const editor = new EasyMDE({
            element: textarea,
            autoDownloadFontAwesome: false,
            previewImagesInEditor: true,
            spellChecker: false,
            forceSync: true,
            status: false,
            tabSize: 4,
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

        attachCopyButton(editor);
        attachSaveShortcut(form);
        attachImagePreview();

        setTimeout(function () {
            editor.codemirror.refresh();
        }, 50);
    });
})();