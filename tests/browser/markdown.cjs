const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
(async () => {
  const browser = await chromium.launch({
    executablePath:
      process.env.CHROME_PATH ||
      "C:/Program Files/Google/Chrome/Application/chrome.exe",
    headless: true,
  });
  try {
    const page = await browser.newPage({
      viewport: { width: 1360, height: 960 },
    });
    const errors = [];
    const external = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.route("**/*", (route) => {
      if (!route.request().url().startsWith("http://127.0.0.1:")) {
        external.push(route.request().url());
        return route.abort();
      }
      return route.continue();
    });
    const source = [
      "## 设备信息",
      "",
      "**供电电压异常**，需要结合现场检查。",
      "",
      "### 排查建议",
      "",
      "- 查询维修记录",
      "- 核对设备型号",
      "",
      "1. 记录报警时间",
      "2. 由合格人员处理",
      "",
      "| 设备 | 状态 |",
      "| --- | --- |",
      "| DEMO-24V | 待排查 |",
      "",
      "```text",
      "<script>仅为代码示例</script>",
      "```",
      "",
      "> 演示资料，不能替代现场检测。",
      "",
      "参考 [KB-demo-1]，查看 [说明](https://example.com/manual)。",
    ].join("\n");
    await page.route("**/api/v1/agent/runs/**", (route) =>
      route.fulfill({
        json: route.request().url().endsWith("/trace")
          ? { metrics: { approval_wait_ms: 0 }, events: [] }
          : {
              id: "c".repeat(32),
              status: "completed",
              result: source,
              pending_action: null,
            },
      }),
    );
    await page.goto(process.env.OPSMIND_WEB_URL || "http://127.0.0.1:8000");
    await page.locator("#run-id").fill("c".repeat(32));
    await page.getByRole("button", { name: "查询", exact: true }).click();
    await page.locator("#answer h2").waitFor();
    assert.equal(await page.locator("#answer h2").textContent(), "设备信息");
    assert.equal(await page.locator("#answer h3").count(), 1);
    assert.equal(await page.locator("#answer strong").count(), 1);
    assert.equal(await page.locator("#answer ul li").count(), 2);
    assert.equal(await page.locator("#answer ol li").count(), 2);
    assert.equal(await page.locator("#answer table th").count(), 2);
    assert.match(
      await page.locator("#answer pre code").textContent(),
      /<script>/,
    );
    assert.equal(await page.locator("#answer script").count(), 0);
    assert.match(await page.locator("#answer").textContent(), /\[KB-demo-1\]/);
    assert.equal(
      await page.locator("#answer a").getAttribute("rel"),
      "noopener noreferrer",
    );
    fs.mkdirSync(".data/ui-checks", { recursive: true });
    await page.screenshot({
      path: ".data/ui-checks/markdown-desktop.png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
    await page.screenshot({
      path: ".data/ui-checks/markdown-mobile.png",
      fullPage: true,
    });
    const attacks = [
      '<script>window.injected=1</script><img src="https://example.com/track" onerror="window.injected=1">',
      '<svg onload="window.injected=1"><a href="javascript:alert(1)">bad</a></svg>',
      '[bad](javascript:alert%281%29) <a href="jav&#x61;script:alert(1)" onclick="window.injected=1">bad</a>',
      '<iframe srcdoc="<script>window.injected=1</script>"></iframe><form id="approve"><input name="current"></form>',
      '<p style="position:fixed" id="status" data-x="1" onmouseover="window.injected=1">text</p><math><mtext><img src=x onerror="window.injected=1"></mtext></math>',
      "[file](file:///etc/passwd) [data](data:text/html,bad) [relative](/api/v1/agent/runs)",
    ];
    for (const input of attacks) {
      await page.evaluate(
        (input) => renderMarkdown(document.getElementById("answer"), input),
        input,
      );
      assert.equal(
        await page
          .locator(
            "#answer script,#answer img,#answer svg,#answer math,#answer iframe,#answer form,#answer input,#answer [style],#answer [id],#answer [onclick],#answer [onerror],#answer a[href]",
          )
          .count(),
        0,
      );
      assert.equal(await page.evaluate(() => window.injected), undefined);
    }
    await page.evaluate(() => {
      window.savedPurify = window.DOMPurify;
      window.DOMPurify = undefined;
      renderMarkdown(
        document.getElementById("answer"),
        "## 原文\n<img onerror=bad>",
      );
    });
    assert.equal(
      await page.locator("#answer").textContent(),
      "## 原文\n<img onerror=bad>",
    );
    assert.equal(await page.locator("#answer img").count(), 0);
    assert.equal(await page.locator("#answer.plain-answer").count(), 1);
    await page.evaluate(() => {
      window.DOMPurify = window.savedPurify;
      renderMarkdown(document.getElementById("answer"), "## 恢复");
    });
    assert.equal(await page.locator("#answer h2").textContent(), "恢复");
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      "Markdown integration, formatting, citations, mobile, XSS, unsafe URLs, no remote assets and safe fallback checks passed.",
    );
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
