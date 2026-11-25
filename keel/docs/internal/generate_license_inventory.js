// One-shot generator for keel/docs/DEPENDENCY-LICENSE-INVENTORY.md.
// Run from the repository root: node keel/docs/internal/generate_license_inventory.js
// Reads installed package metadata only; no license is inferred.
const fs = require('fs');
const path = require('path');

const trees = [
  ['keel/fleet-next/node_modules', 'fleet-next'],
  ['keel/desktop-app/node_modules', 'keel-desktop'],
];

function collect(root) {
  const rows = [];
  function walk(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue;
      const full = path.join(dir, entry.name);
      const file = path.join(full, 'package.json');
      if (fs.existsSync(file)) {
        try {
          const json = JSON.parse(fs.readFileSync(file, 'utf8'));
          const license = typeof json.license === 'string'
            ? json.license
            : (json.license ? '`' + JSON.stringify(json.license) + '`' : 'UNDECLARED');
          rows.push([json.name || entry.name, json.version || '', license]);
        } catch (_) { /* unreadable metadata is not evidence */ }
      }
      if (entry.name.startsWith('@')) walk(full);
    }
  }
  walk(root);
  rows.sort((a, b) => a[0].localeCompare(b[0]));
  return rows;
}

const out = [
  '# Dependency license inventory (generated from installed metadata)',
  '',
  'Generated 2026-11-24 from the installed `node_modules` trees in this worktree. This is a documentation artifact, not a generated feature registry.',
  '',
  'Both `package-lock.json` files are lockfileVersion 3 and contain **no `license` field** on any `packages` entry. No license below was inferred from a lockfile or from a package name: every SPDX expression is read from that package\'s own `package.json` `license` field. `UNDECLARED` means the field is absent.',
  '',
  'Regenerate from the repository root with `node .verify-license-inventory-gen.js`.',
  '',
];

for (const [root, label] of trees) {
  out.push('## ' + label + ' tree', '', '| Package | Version | Declared license (`package.json`) |', '|---|---|---|');
  for (const row of collect(root)) out.push('| ' + row.join(' | ') + ' |');
  out.push('');
}

out.push(
  '## Python environment (observed on this audit host)',
  '',
  '| Distribution | Version | `License-Expression` / `License` metadata |',
  '|---|---|---|',
  '| tzdata | 2026.5 | Apache-2.0 |',
  '| cryptography | 50.0.1 | Apache-2.0 OR BSD-3-Clause |',
  '| pillow | 11.1.0 | MIT-CMU |',
  '| certifi | 2026.7.22 | MPL-2.0 |',
  '| setuptools | 84.0.0 | MIT |',
  '| pyinstaller | 6.19.0 | GPLv2-or-later with a special exception which allows to use PyInstaller to build and distribute non-free programs (including commercial ones) |',
  '| pytest | 9.0.2 | MIT |',
  '',
  '`keyring` is declared in `keel/pyproject.toml` but is **not installed** on this host, so no local distribution metadata was available this round. Its MIT status is recorded in `keel/docs/proprietary/THIRD_PARTY_NOTICES.draft.md` from an earlier installed-metadata audit and is carried forward as historical evidence, not as a fresh observation.',
  '',
);

fs.writeFileSync('keel/docs/DEPENDENCY-LICENSE-INVENTORY.md', out.join('\n'));
console.log('wrote keel/docs/DEPENDENCY-LICENSE-INVENTORY.md, ' + out.length + ' lines');
