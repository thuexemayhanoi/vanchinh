// validate_content_matrix.mjs - Node fallback for scripts/validate_content_matrix.py
// Deterministic matrix integrity gate. Usage: node scripts/validate_content_matrix.mjs
import fs from 'fs';
import path from 'path';

const ROOT = path.resolve(import.meta.dirname, '..');
const MATRIX = path.join(ROOT, 'data', 'content-matrix.csv');
const EXPECTED = { KN: 350, AT: 300, XM: 350, DL: 400, CD: 300, HD: 300 };
const STATES = new Set(['PLANNED', 'WRITING', 'QA', 'REVIEW', 'REPAIR', 'PASS', 'PUBLISHED', 'FAIL', 'BLOCKED']);
const HUBS = { KN: 'kinhnghiem.html', AT: 'antoan.html', XM: 'xemay.html', DL: 'dulich.html', CD: 'cungduong.html', HD: 'hoidap.html' };
// Navigation taxonomy contract: exactly 3 public groups over 6 canonical categories
const NAV_GROUPS = [
  { name: 'Thuê xe & Hỏi đáp', hubs: ['kinhnghiem.html', 'hoidap.html'], categories: ['KN', 'HD'] },
  { name: 'Xe máy & An toàn', hubs: ['xemay.html', 'antoan.html'], categories: ['XM', 'AT'] },
  { name: 'Du lịch & Cung đường', hubs: ['dulich.html', 'cungduong.html'], categories: ['DL', 'CD'] },
];
const allHubs = NAV_GROUPS.flatMap(g => g.hubs).sort().join(',');
if (allHubs !== Object.values(HUBS).sort().join(',')) errors.push('nav groups do not cover exactly the 6 canonical hubs');
const allCats = NAV_GROUPS.flatMap(g => g.categories).sort().join(',');
if (allCats !== Object.keys(HUBS).sort().join(',')) errors.push('nav groups do not cover exactly the 6 canonical categories');

function parseCSV(text) {
  const lines = text.split('\n');
  const header = lines[0].split(',');
  return lines.slice(1).filter(l => l.trim()).map(line => {
    const cells = [];
    let cur = '', inQ = false;
    for (const ch of line) {
      if (ch === '"') inQ = !inQ;
      else if (ch === ',' && !inQ) { cells.push(cur); cur = ''; }
      else cur += ch;
    }
    cells.push(cur);
    const row = {};
    header.forEach((h, i) => row[h] = cells[i] ?? '');
    return row;
  });
}

const errors = [];
const rows = parseCSV(fs.readFileSync(MATRIX, 'utf-8'));
if (rows.length !== 2000) errors.push(`row count ${rows.length} != 2000`);
const ids = new Set(), paths = new Set(), cats = {}, batches = {};
for (const r of rows) {
  if (ids.has(r.article_id)) errors.push(`duplicate id ${r.article_id}`);
  ids.add(r.article_id);
  if (paths.has(r.output_path)) errors.push(`duplicate path ${r.output_path}`);
  paths.add(r.output_path);
  cats[r.category] = (cats[r.category] || 0) + 1;
  if (!STATES.has(r.status)) errors.push(`${r.article_id}: bad status ${r.status}`);
  if (r.parent_hub !== HUBS[r.category]) errors.push(`${r.article_id}: bad parent_hub`);
  if (!r.output_path.startsWith('cam-nang/')) errors.push(`${r.article_id}: path not under cam-nang/`);
  batches[r.batch_id] = (batches[r.batch_id] || 0) + 1;
}
for (const [c, n] of Object.entries(EXPECTED)) if (cats[c] !== n) errors.push(`cat ${c}: ${cats[c]} != ${n}`);
const bkeys = Object.keys(batches);
if (bkeys.length !== 40) errors.push(`batches ${bkeys.length} != 40`);
for (const b of bkeys) if (batches[b] !== 50) errors.push(`batch ${b}: ${batches[b]} != 50`);
for (const e of errors) console.log('ERROR:', e);
console.log(`matrix rows=${rows.length} cats=${JSON.stringify(cats)} batches=${bkeys.length} errors=${errors.length}`);
process.exit(errors.length ? 1 : 0);
