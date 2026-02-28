(function () {

    function normalizeFaviconDomain(host) {
        host = (host || "").replace(/^www\./i, "").toLowerCase();

        if (host === "maps.app.goo.gl") return "maps.google.com";
        if (host.endsWith(".goo.gl")) return "google.com";

        return host;
    }

    function stylizeExternalLinks() {
        let internal = (location.host || "").replace("www.", "");
        internal = new RegExp(internal, "i");

        const post = document.querySelector(".post");
        if (!post) return;
        const links = Array.from(post.querySelectorAll(".block-text a, figcaption a"));

        links.forEach((link) => {
            if (!link.host) return;
            if (internal.test(link.host)) return;
            if (link.querySelector(".link-favicon")) return;

            link.setAttribute("target", "_blank");
            link.setAttribute("rel", "noopener");

            const rawHost = link.host.split(":")[0];
            const domain = normalizeFaviconDomain(rawHost);
            const img = document.createElement("img");
            img.src = `https://www.google.com/s2/favicons?domain=${domain}&sz=32`;
            img.className = "link-favicon";
            img.alt = "";
            img.decoding = "async";
            img.loading = "lazy";
            img.referrerPolicy = "no-referrer";

            link.insertBefore(img, link.firstChild);
            link.insertBefore(document.createTextNode("\u00A0"), img.nextSibling);
      });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", stylizeExternalLinks);
    } else {
        stylizeExternalLinks();
    }
    
})();