# CesiumJS 1.146.0, as vendored by Orbit

Source: the npm package `cesium@1.146.0` (tarball sha256
`9e4166f2d61e1088c94c1161ab92493750959160e5a37893a8b8c50c494048d5`), `Build/Cesium/` without `index.js` and
`index.cjs`, plus the package's `LICENSE.md` (Apache-2.0) and `ThirdParty.json`. Every file is unchanged except
`Cesium.js`, which carries one patch.

## The patch (16 Nov 2026)
Cesium.js bundles Knockout 3.5.1, which finds the global object with `(0,eval)("this")` when the file loads. Orbit's
CSP has no `'unsafe-eval'`, so that throws and Cesium never loads. Orbit uses `CesiumWidget` only, not the Viewer
widgets that need Knockout's eval-based bindings, so the one expression is replaced:

    var t=this||(0,eval)("this"),n=t.document   ->   var t=this||globalThis,n=t.document

- Original `Cesium.js` sha256: `a5ab7e638f51d3bc5a6c710a79c9aecea42d9252b5cd2dad34980ea771c2c9af`
- Patched `Cesium.js` sha256: `55afd1d973a6ae118e596c56f24f7441a9c8ea62fec7626e6915670093d38230`

Both hashes are of the file with LF line ends, as published (git on Windows may check it out with CRLF).
`tests/test_globe.py` checks the patch and this hash. On an upgrade, apply the same patch and update both hashes.

## Not patched, handled elsewhere
- Workers: Cesium.js starts its workers from `blob:` URLs built from the `CESIUM_WORKERS` string, which
  `script-src 'self'` refuses. `globe.js` sets `globalThis.CESIUM_WORKERS = undefined` after loading Cesium, so
  Cesium starts the same workers as ES modules from `Workers/` on Orbit's origin.
- WebAssembly: Cesium compiles WebAssembly as it loads; the CSP allows `'wasm-unsafe-eval'` (WebAssembly only, not
  JavaScript eval).
- Styles: Cesium's credit display injects two fixed `<style>` blocks, allowed by their sha256 hashes in
  `style-src`. A few inline `style` attributes in its credit markup stay blocked, which only affects how the credit looks.
