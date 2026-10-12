# Browser dependencies

- Marked 18.1.0: Markdown / GFM parser, MIT. Source: https://github.com/markedjs/marked
- DOMPurify 3.4.16: HTML sanitizer, Apache-2.0 OR MPL-2.0. Source: https://github.com/cure53/DOMPurify

Files copied from official npm package tarballs, verified against registry SHA-512 integrity. Versions, URLs, tarball integrity and asset SHA-256 are recorded in manifest.json. License texts are retained alongside assets. No CDN requests at runtime. Update pinned assets and manifest together after checking upstream security releases, then run tests/browser/markdown.cjs.

Marked does not sanitize output: https://marked.js.org/ . The app sanitizes before inserting a DOM fragment. Allowed formatting tags only; no images, scripts, forms, SVG, styles, IDs or event attributes. Links are limited to absolute HTTP(S) URLs with no opener/referrer. Parser or sanitizer failures fall back to textContent. These libraries are frontend runtime assets; no Node build step is required to start OpsMind.
