"use strict";
// Drives the live refresh against a real HTTP server. The Python test controls the server and sends commands
// on stdin ("go", "stop", "restart"); this script reports what the page did on stdout.
const readline = require("readline");
const { openPage, rows, selectedId, status, waitFor } = require("./helpers");

const lines = [];
const waiting = [];
readline.createInterface({ input: process.stdin }).on("line", (line) => {
  if (waiting.length) waiting.shift()(line.trim());
  else lines.push(line.trim());
});
const nextCommand = () =>
  new Promise((resolve) =>
    lines.length ? resolve(lines.shift()) : waiting.push(resolve),
  );
const say = (text) => process.stdout.write(text + "\n");

async function main() {
  const base = process.argv[2];
  const dom = await openPage(base + "/?refresh=250");

  await waitFor(() => rows(dom).length > 0, "initial rows");
  const initialRows = rows(dom).length;
  rows(dom)[initialRows - 1].dispatchEvent(new dom.window.Event("click"));
  const chosen = selectedId(dom);
  say(`READY rows=${initialRows} selected=${chosen}`);

  if ((await nextCommand()) !== "go") throw new Error("expected go");
  await waitFor(
    () => rows(dom).length > initialRows,
    "a new row to appear through polling",
  );
  await waitFor(() => /^Live: updated/.test(status(dom)), "live status");
  if (selectedId(dom) !== chosen)
    throw new Error(`selection changed from ${chosen} to ${selectedId(dom)}`);
  say(`UPDATED rows=${rows(dom).length} selected=${selectedId(dom)}`);

  if ((await nextCommand()) !== "stop") throw new Error("expected stop");
  await waitFor(
    () => /paused/.test(status(dom)),
    "paused status after the server stopped",
  );
  say(`PAUSED rows=${rows(dom).length}`);

  if ((await nextCommand()) !== "restart") throw new Error("expected restart");
  await waitFor(
    () => /^Live: updated/.test(status(dom)),
    "recovery after the server came back",
  );
  say("RECOVERED");

  dom.window.close();
  say("DONE");
  process.exit(0);
}

main().catch((error) => {
  say("FAIL " + error.message);
  process.exit(1);
});
