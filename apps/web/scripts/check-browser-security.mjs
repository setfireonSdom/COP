// CI preflight: no pages or project requests; the same guard also runs in each
// E2E worker. Never replace this with a version-print command or bundled install.
import { launchChrome } from "./safe-browser.mjs";

const browser = await launchChrome();
try {
  console.log(`System Chrome ${browser.version()}: version policy passed; sandbox requested.`);
} finally {
  await browser.close();
}
