// Refresh the "recent notes" list in README.md from my YouTube channel and my
// blog's RSS feed. No dependencies; run with Node 20+:
//   node scripts/update_notes.mjs
import { readFile, writeFile } from 'node:fs/promises';

const README = new URL('../README.md', import.meta.url);
const YOUTUBE = 'https://www.youtube.com/feeds/videos.xml?channel_id=UCAkpuFPaycl9WflYoyiTpUQ';
const BLOG = 'https://harshpreet.com/feed.xml';
const VIDEOS = 3;
const POSTS = 3;

const ENTITIES = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" };

function unescape(s) {
  return s
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1')
    .replace(/&#(x?)([0-9a-f]+);/gi, (_, x, n) => String.fromCodePoint(parseInt(n, x ? 16 : 10)))
    .replace(/&(\w+);/g, (m, name) => ENTITIES[name] ?? m)
    .trim();
}

function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function tag(xml, name) {
  const m = xml.match(new RegExp(`<${name}[^>]*>([\\s\\S]*?)</${name}>`));
  return m ? unescape(m[1]) : '';
}

function blocks(xml, name) {
  return [...xml.matchAll(new RegExp(`<${name}>([\\s\\S]*?)</${name}>`, 'g'))].map((m) => m[1]);
}

async function fetchText(url) {
  const res = await fetch(url, { headers: { 'user-agent': 'harshpreet931-readme' } });
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  return res.text();
}

async function videos() {
  const xml = await fetchText(YOUTUBE);
  return blocks(xml, 'entry').map((e) => ({
    title: tag(e, 'title'),
    url: e.match(/<link rel="alternate" href="([^"]+)"/)?.[1],
    date: new Date(tag(e, 'published')),
    kind: 'video',
  }));
}

async function posts() {
  const xml = await fetchText(BLOG);
  return blocks(xml, 'item').map((i) => ({
    title: tag(i, 'title'),
    url: tag(i, 'link'),
    date: new Date(tag(i, 'pubDate')),
    kind: 'post',
  }));
}

function render(items) {
  const month = new Intl.DateTimeFormat('en', { month: 'short', year: 'numeric', timeZone: 'UTC' });
  return items
    .map((n) => `<a href="${escapeHtml(n.url)}">${escapeHtml(n.title)}</a> <sub>${n.kind}&nbsp;·&nbsp;${month.format(n.date).toLowerCase().replace(' ', '&nbsp;')}</sub>`)
    .join('<br>\n');
}

const newest = (a, b) => b.date - a.date;
const valid = (n) => n.title && n.url && !Number.isNaN(n.date.getTime());

// YouTube's feed fails now and then. Keep yesterday's list rather than
// publishing half of it.
let v, p;
try {
  [v, p] = await Promise.all([videos(), posts()]);
} catch (err) {
  console.warn(`skipping refresh: ${err.message}`);
  process.exit(0);
}
const items = [
  ...v.filter(valid).sort(newest).slice(0, VIDEOS),
  ...p.filter(valid).sort(newest).slice(0, POSTS),
];
if (items.length === 0) throw new Error('both feeds came back empty; leaving README alone');

const readme = await readFile(README, 'utf8');
const next = readme.replace(
  /(<!-- notes:start -->)[\s\S]*?(<!-- notes:end -->)/,
  `$1\n${render(items)}\n$2`
);
if (next === readme) {
  console.log('notes unchanged');
} else {
  await writeFile(README, next);
  console.log(`notes updated: ${items.length} items`);
}
