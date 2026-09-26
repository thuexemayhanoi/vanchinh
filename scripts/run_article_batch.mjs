// run_article_batch.mjs - Node fallback (read-only plan + progress writer).
// The Python tool (run_article_batch.py) is the authoritative orchestrator with
// lock/transaction/publish; this fallback supports plan/progress when Python is unavailable.
import fs from 'fs';
import path from 'path';
import { execFileSync } from 'child_process';

const ROOT = path.resolve(import.meta.dirname, '..');
const cmd = process.argv[2];

function loadMatrix() {
  const text = fs.readFileSync(path.join(ROOT, 'data', 'content-matrix.csv'), 'utf-8');
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
    const row = {}; header.forEach((h, i) => row[h] = cells[i] ?? ''); return row;
  });
}

function writeProgress(rows) {
  const counts = {};
  for (const r of rows) counts[r.status] = (counts[r.status] || 0) + 1;
  const batches = {};
  for (const r of rows) {
    batches[r.batch_id] = batches[r.batch_id] || { total: 0, published: 0 };
    batches[r.batch_id].total++;
    if (r.status === 'PUBLISHED') batches[r.batch_id].published++;
  }
  const keys = Object.keys(batches).sort();
  const completed = keys.filter(b => batches[b].published === batches[b].total);
  const active = keys.find(b => batches[b].published > 0 && batches[b].published < batches[b].total) || null;
  const next = keys.find(b => batches[b].published === 0) || null;
  const prev = fs.existsSync(path.join(ROOT, 'reports/batches/factory-progress.json'))
    ? JSON.parse(fs.readFileSync(path.join(ROOT, 'reports/batches/factory-progress.json'), 'utf-8')) : {};
  const out = {
    generated: new Date().toISOString().replace(/\.\d+Z$/, 'Z'),
    total: rows.length,
    planned: counts.PLANNED || 0, writing: counts.WRITING || 0, qa: counts.QA || 0,
    review: counts.REVIEW || 0, repair: counts.REPAIR || 0, pass: counts.PASS || 0,
    published: counts.PUBLISHED || 0, fail: counts.FAIL || 0, blocked: counts.BLOCKED || 0,
    completed_batches: completed.length, active_batch: active, next_batch: next,
    published_commit_sha: prev.published_commit_sha || '',
  };
  fs.mkdirSync(path.join(ROOT, 'reports/batches'), { recursive: true });
  fs.writeFileSync(path.join(ROOT, 'reports/batches/factory-progress.json'), JSON.stringify(out, null, 2));
  console.log(JSON.stringify(out, null, 2));
}

if (cmd === 'plan') {
  const batch = process.argv[3];
  const rows = loadMatrix().filter(r => r.batch_id === batch);
  const unfinished = rows.filter(r => !['PUBLISHED', 'BLOCKED'].includes(r.status)).map(r => r.article_id);
  console.log(JSON.stringify({ batch, total: rows.length,
    published: rows.filter(r => r.status === 'PUBLISHED').length, unfinished }, null, 2));
} else if (cmd === 'progress') {
  writeProgress(loadMatrix());
} else {
  console.log('usage: node scripts/run_article_batch.mjs <plan|progress> [batch_id]');
  console.log('note: claim/qa/publish require the Python orchestrator (lock + transaction).');
  process.exit(2);
}
