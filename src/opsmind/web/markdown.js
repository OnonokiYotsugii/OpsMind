"use strict";

// Sanitize before insertion. Keep approval parameters on the separate text-only path.
function renderMarkdown(container, source) {
  const text = String(source ?? "");
  container.classList.remove("plain-answer");
  try {
    if (!globalThis.marked || !globalThis.DOMPurify?.isSupported) {
      throw new Error("Markdown dependencies unavailable");
    }
    const html = marked.parse(text, { gfm: true, breaks: false, async: false });
    const fragment = DOMPurify.sanitize(html, {
      ALLOWED_TAGS: [
        "p",
        "br",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "strong",
        "em",
        "del",
        "ul",
        "ol",
        "li",
        "blockquote",
        "pre",
        "code",
        "hr",
        "a",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
      ],
      ALLOWED_ATTR: ["href", "title", "start"],
      ALLOW_DATA_ATTR: false,
      ALLOW_ARIA_ATTR: false,
      RETURN_DOM_FRAGMENT: true,
    });
    for (const link of fragment.querySelectorAll("a")) {
      try {
        const url = new URL(link.getAttribute("href"));
        if (!["https:", "http:"].includes(url.protocol))
          throw new Error("Unsafe URL");
        link.setAttribute("target", "_blank");
        link.setAttribute("rel", "noopener noreferrer");
        link.setAttribute("referrerpolicy", "no-referrer");
      } catch {
        link.removeAttribute("href");
      }
    }
    for (const table of fragment.querySelectorAll("table")) {
      const wrap = document.createElement("div");
      wrap.className = "answer-table";
      wrap.tabIndex = 0;
      wrap.setAttribute("role", "region");
      wrap.setAttribute("aria-label", "回答表格，可横向滚动");
      table.replaceWith(wrap);
      wrap.append(table);
    }
    container.replaceChildren(fragment);
  } catch {
    // A failed parser/filter must never fall back to unsanitized innerHTML.
    container.classList.add("plain-answer");
    container.textContent = text;
  }
}
