import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repository = path.dirname(frontend);
const artifacts = path.join(frontend, 'test-results');
fs.mkdirSync(artifacts, {recursive: true});
const runDirectory = fs.mkdtempSync(path.join(artifacts, 'run-'));
const python = process.env.FLOWBRIDGE_PYTHON || path.join(repository, '.venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const apiBase = 'http://127.0.0.1:8877';
const uiBase = 'http://127.0.0.1:5188';
const processes = [];
const report = {};

function launch(executable, args, options) {
  const child = spawn(executable, args, {windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'], ...options});
  child.logs = '';
  child.stdout.on('data', bytes => child.logs += bytes);
  child.stderr.on('data', bytes => child.logs += bytes);
  processes.push(child);
  return child;
}

async function ready(url, process) {
  for (let attempt = 0; attempt < 100; attempt++) {
    if (process.exitCode !== null) throw new Error(process.logs);
    try { if ((await fetch(url)).ok) return; } catch {}
    await new Promise(resolve => setTimeout(resolve, 150));
  }
  throw new Error(`Server did not start: ${process.logs}`);
}

let browser;
let page;
try {
  const backend = launch(python, ['-m', 'uvicorn', 'browser_app:app', '--app-dir', path.join(repository, 'tests'),
    '--host', '127.0.0.1', '--port', '8877'], {cwd: repository,
    env: {...process.env, PYTHONDONTWRITEBYTECODE: '1', FLOWBRIDGE_E2E_OUTPUT_DIR: runDirectory}});
  const ui = launch(process.execPath, [path.join(frontend, 'node_modules/vite/bin/vite.js'),
    '--host', '127.0.0.1', '--port', '5188', '--strictPort'], {cwd: frontend,
    env: {...process.env, VITE_API_BASE_URL: apiBase}});
  await ready(`${apiBase}/_browser_fixture`, backend);
  assert.equal((await (await fetch(`${apiBase}/_browser_fixture`)).json()).fixture, 'flowbridge-browser-check');
  await ready(uiBase, ui);
  browser = await chromium.launch({headless: true,
    ...(process.env.FLOWBRIDGE_BROWSER_EXECUTABLE ? {executablePath: process.env.FLOWBRIDGE_BROWSER_EXECUTABLE} : {})});
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}, acceptDownloads: true});
  page = await context.newPage();
  const browserErrors = [];
  page.on('pageerror', error => browserErrors.push(error.message));
  await page.goto(uiBase, {waitUntil: 'networkidle'});

  await page.getByRole('button', {name: 'Import public GitHub repository'}).click();
  await page.getByLabel('Repository URL').fill('https://github.com/demo/repo');
  const [importResponse] = await Promise.all([
    page.waitForResponse(response => response.url().endsWith('/api/projects/github')),
    page.getByRole('button', {name: 'Import repository', exact: true}).click(),
  ]);
  assert.equal(importResponse.status(), 201);
  assert.deepEqual(importResponse.request().postDataJSON(), {url: 'https://github.com/demo/repo'});
  const project = await importResponse.json();
  assert.equal(project.files.length, 3);
  await page.waitForFunction(() => !document.querySelector('dialog').open);
  await page.getByRole('button', {name: 'Analyze project'}).click();
  await page.waitForFunction(() => document.querySelectorAll('.react-flow__edge').length > 0);
  await page.getByRole('button', {name: 'main.py', exact: true}).click();
  await page.locator('.react-flow__node').filter({hasText: 'message ='}).click();
  await page.waitForFunction(() => document.querySelector('mark')?.textContent === 'message = "café 😀"');
  report.githubImportAndUnicodeHighlight = 'passed';

  await page.locator('.react-flow__node').filter({hasText: 'total: int = adjust(2)'}).dblclick();
  await page.waitForFunction(() => document.querySelector('#diagramView option:checked')?.textContent.includes('adjust()'));
  await page.locator('.react-flow__node').filter({hasText: 'value > 0'}).click();
  await page.waitForFunction(() => document.querySelector('mark')?.textContent === 'value > 0');
  await page.getByRole('button', {name: 'Back', exact: true}).click();
  await page.getByLabel('View', {exact: true}).selectOption({label: 'Project overview'});
  await page.waitForFunction(() => [...document.querySelectorAll('.react-flow__edge-text')].some(node => node.textContent === 'imports'));
  report.navigationEdgesAndSourceLookup = 'passed';

  await page.getByRole('button', {name: 'Export diagrams', exact: true}).click();
  const viewerLink = page.getByRole('link', {name: 'Open SVG viewer'});
  await viewerLink.waitFor();
  const firstViewerUrl = await viewerLink.getAttribute('href');
  const [viewer] = await Promise.all([page.waitForEvent('popup'), viewerLink.click()]);
  await viewer.waitForLoadState('networkidle');
  assert.ok(await viewer.locator('svg').count());
  const exported = await fetch(`${apiBase}/api/projects/${project.projectID}/render`, {method: 'POST'});
  const manifest = await (await fetch(apiBase + (await exported.json()).manifestUrl)).json();
  const paths = manifest.graphs.map(graph => graph.path);
  assert.equal(new Set(paths).size, paths.length);
  const [download] = await Promise.all([viewer.waitForEvent('download'), viewer.getByRole('button', {name: /Export SVG/}).click()]);
  assert.ok(download.suggestedFilename().endsWith('.svg'));
  await viewer.close();
  report.svgExport = 'passed';

  await page.getByRole('button', {name: 'Import public GitHub repository'}).click();
  await page.getByLabel('Repository URL').fill('https://github.com/demo/missing');
  await page.getByRole('button', {name: 'Import repository', exact: true}).click();
  await page.getByRole('alert').waitFor();
  assert.equal(await page.getByRole('button', {name: 'nested/main.py', exact: true}).count(), 1);
  await page.getByRole('button', {name: 'Cancel', exact: true}).click();
  report.failedImportKeepsProject = 'passed';

  await page.locator('#fileUpload').setInputFiles({name: 'local.py', mimeType: 'text/x-python', buffer: Buffer.from('x = 1\n')});
  await page.getByRole('button', {name: 'local.py', exact: true}).waitFor();
  await page.getByRole('button', {name: 'Analyze project'}).click();
  await page.waitForFunction(() => document.querySelectorAll('.react-flow__edge').length > 0);
  assert.equal((await fetch(firstViewerUrl)).status, 200);
  report.regularUploadAndExportIsolation = 'passed';

  const zip = await (await fetch(`${apiBase}/_browser_fixture/archive.zip`)).arrayBuffer();
  await page.locator('#fileUpload').setInputFiles({name: 'project.zip', mimeType: 'application/zip', buffer: Buffer.from(zip)});
  await page.getByRole('button', {name: 'demo-repo-abcdef1/nested/main.py', exact: true}).waitFor();
  await page.getByRole('button', {name: 'Analyze project'}).click();
  await page.waitForFunction(() => document.querySelectorAll('.react-flow__edge').length > 0);
  await page.getByRole('button', {name: 'Export diagrams', exact: true}).click();
  await page.getByRole('link', {name: 'Open SVG viewer'}).waitFor();
  assert.notEqual(await page.getByRole('link', {name: 'Open SVG viewer'}).getAttribute('href'), firstViewerUrl);
  assert.equal((await fetch(firstViewerUrl)).status, 200);
  report.zipUploadAndDuplicateNames = 'passed';
  assert.deepEqual(browserErrors, []);
  report.browserErrors = browserErrors;
  console.log(JSON.stringify(report, null, 2));
} catch (error) {
  report.error = error.message;
  if (page) await page.screenshot({path: path.join(artifacts, 'browser-failure.png'), fullPage: true}).catch(() => {});
  console.error(error);
  for (const process of processes) console.error(process.logs);
  process.exitCode = 1;
} finally {
  fs.writeFileSync(path.join(artifacts, 'browser-last.json'), JSON.stringify(report, null, 2));
  if (browser) await browser.close();
  for (const child of processes) {
    if (child.exitCode === null) {
      const exited = once(child, 'exit');
      child.kill();
      await Promise.race([exited, new Promise(resolve => setTimeout(resolve, 2000))]);
    }
  }
  const target = path.resolve(runDirectory);
  if (target.startsWith(path.resolve(artifacts) + path.sep) && path.basename(target).startsWith('run-')) {
    fs.rmSync(target, {recursive: true, force: true, maxRetries: 3, retryDelay: 100});
  }
}
