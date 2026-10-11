// UI fixtures only; business correctness remains covered by real MySQL tests.
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
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(process.env.OPSMIND_WEB_URL || "http://127.0.0.1:8010");
    await page.getByText("后端在线 · 数据库待查询").waitFor();
    fs.mkdirSync("docs/images", { recursive: true });
    await page.screenshot({
      path: "docs/images/workspace.png",
      fullPage: true,
    });
    const id = "a".repeat(32),
      action = "b".repeat(32);
    let requests = 0,
      decisions = [];
    const pending = {
      id,
      status: "waiting_confirmation",
      pending_action: {
        action_id: action,
        tool: "create_ticket",
        arguments: {
          equipment_no: "EQ-10023",
          title: '<img src=x onerror="window.injected=true">',
        },
        expires_at: "2099-01-01T00:00:00Z",
      },
      result: null,
    };
    let result = pending;
    await page.route("**/api/v1/agent/runs**", async (route) => {
      const request = route.request();
      if (request.url().endsWith("/trace"))
        return route.fulfill({
          json: {
            metrics: {
              model_calls: 1,
              tool_calls: 1,
              observed_processing_ms: 8,
              token_usage: null,
              approval_wait_ms: 0,
            },
            events: [
              {
                kind: "retrieval",
                items: [
                  {
                    citation: "KB-test",
                    source: "demo-power",
                    heading: "E102",
                    version: "1.0",
                  },
                ],
              },
            ],
          },
        });
      if (request.url().endsWith("/decisions")) {
        decisions.push(request.postDataJSON());
        await new Promise((resolve) => setTimeout(resolve, 180));
        result = {
          id,
          status: request.postDataJSON().approved ? "completed" : "rejected",
          pending_action: null,
          result: "<script>window.injected=true</script>",
        };
        return route.fulfill({ json: result });
      }
      if (request.method() === "POST") {
        requests++;
        result = pending;
      }
      return route.fulfill({ json: result });
    });
    await page.getByRole("button", { name: "创建工单", exact: true }).click();
    assert.equal(requests, 0, "example must not call model");
    await page.getByRole("button", { name: "开始处理" }).click();
    await page.getByRole("button", { name: "确认执行", exact: true }).waitFor();
    assert.equal(await page.locator("#arguments img").count(), 0);
    await page.getByRole("button", { name: "确认执行", exact: true }).click();
    assert.equal(
      await page
        .getByRole("button", { name: "确认执行", exact: true })
        .isDisabled(),
      true,
    );
    await page.getByText("已完成", { exact: true }).waitFor();
    assert.deepEqual(decisions, [{ action_id: action, approved: true }]);
    assert.equal(await page.evaluate(() => window.injected), undefined);
    await page.getByRole("button", { name: "开始处理" }).click();
    await page.getByRole("button", { name: "拒绝操作", exact: true }).click();
    await page.getByText("已拒绝", { exact: true }).waitFor();
    assert.equal(decisions[1].approved, false);
    await page.unroute("**/api/v1/agent/runs**");
    await page.route("**/api/v1/agent/runs**", (r) =>
      r.fulfill({
        status: 503,
        json: { error: { code: "database_unavailable" } },
      }),
    );
    await page.getByRole("button", { name: "刷新状态" }).click();
    await page
      .getByRole("alert")
      .filter({ hasText: "database_unavailable" })
      .waitFor();
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
    await page.goto(process.env.OPSMIND_WEB_URL || "http://127.0.0.1:8010");
    await page.getByText("后端在线 · 数据库待查询").waitFor();
    await page.locator("#run-id").fill("");
    await page.screenshot({
      path: "docs/images/workspace-mobile.png",
      fullPage: true,
    });
    assert.deepEqual(errors, []);
    console.log(
      "UI checks passed: initial render, example safety, approval binding, duplicate lock, rejection, XSS text, errors, mobile layout.",
    );
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
