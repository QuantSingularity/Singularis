"use strict";
const { JSDOM } = require("jsdom");

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitFor(predicate, description, timeoutMs = 10000) {
  const started = Date.now();
  for (;;) {
    const value = predicate();
    if (value) return value;
    if (Date.now() - started > timeoutMs)
      throw new Error("timed out waiting for " + description);
    await sleep(50);
  }
}

// jsdom has no fetch, so give the page the real one from Node, resolving relative URLs against the page.
function openPage(url) {
  return JSDOM.fromURL(url, {
    runScripts: "dangerously",
    pretendToBeVisual: true,
    beforeParse(window) {
      window.fetch = (target, options) =>
        fetch(new URL(target, window.location.href), options);
    },
  });
}

const rows = (dom) => dom.window.document.querySelectorAll("#rows tr");
const selectedId = (dom) => {
  const row = dom.window.document.querySelector("#rows tr.sel");
  return row ? row.firstChild.textContent : null;
};
const status = (dom) =>
  dom.window.document.getElementById("status").textContent;

module.exports = { sleep, waitFor, openPage, rows, selectedId, status };
