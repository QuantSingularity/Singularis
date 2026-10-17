"use strict";
// Renders the sample report in a simulated browser and checks structure, safety, and error handling.
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
const sample = fs.readFileSync(
  path.join(root, "sample", "report.json"),
  "utf8",
);

const errors = [];
const dom = new JSDOM(html, {
  runScripts: "dangerously",
  url: "file:///index.html",
});
dom.window.addEventListener("error", (event) => errors.push(event.message));
const { window } = dom;
const doc = window.document;

window.singularisLoadReport(sample);
const agents = JSON.parse(sample).agents.length;
assert.strictEqual(doc.getElementById("app").hidden, false);
assert.strictEqual(doc.querySelectorAll("#rows tr").length, agents);
assert.ok(doc.querySelectorAll("#summary .card").length >= 6);
assert.strictEqual(doc.querySelectorAll("svg circle").length, agents);
assert.ok(doc.querySelectorAll("#meta tbody tr").length >= 1);

doc.querySelectorAll("#rows tr")[1].dispatchEvent(new window.Event("click"));
assert.match(doc.querySelector("#detail h2").textContent, /child of a0000/);

const hostile = JSON.parse(sample);
hostile.agents[0].note = "<img src=x onerror=alert(1)>";
hostile.agents[0].diff = "+<script>window.pwned=1</script>\n";
hostile.agents[0].focus = "<b>bold</b>";
window.singularisLoadReport(JSON.stringify(hostile));
doc.querySelectorAll("#rows tr")[0].dispatchEvent(new window.Event("click"));
assert.strictEqual(
  doc.querySelectorAll("#app img, #app script, #app b").length,
  0,
);
assert.strictEqual(window.pwned, undefined);

assert.strictEqual(window.singularisLoadReport("not json"), false);
assert.match(doc.getElementById("status").textContent, /Could not load report/);
assert.strictEqual(
  window.singularisLoadReport(JSON.stringify({ agents: [] })),
  true,
);
assert.match(doc.getElementById("chart").textContent, /No evaluated agents/);
assert.deepStrictEqual(errors, []);
console.log("render checks passed");
