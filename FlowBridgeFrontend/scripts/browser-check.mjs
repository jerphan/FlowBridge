import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const review = path.dirname(frontend);
const artifacts = path.join(frontend, 'test-results');
fs.mkdirSync(artifacts, {recursive: true});
const output = fs.mkdtempSync(path.join(artifacts, 'run-'));
const apiBase = 'http://127.0.0.1:8877';
const python = process.env.FLOWBRIDGE_PYTHON || path.join(review, '.venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const env = {...process.env, PYTHONDONTWRITEBYTECODE: '1', FLOWBRIDGE_E2E_OUTPUT_DIR: output,
  VITE_API_BASE_URL: apiBase,
  PYTHONPATH: [review, path.join(review, 'FlowBridge_ParsingAndAnalysis/src'), path.join(review, 'tests')].join(path.delimiter)};
let serverLog = '';
const processes = [
  spawn(python, ['-m', 'uvicorn', 'browser_app:app', '--host', '127.0.0.1', '--port', '8877'],
    { cwd: output, env, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] }),
  spawn(process.execPath, [path.join(frontend, 'node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '5188', '--strictPort'],
    { cwd: frontend, env, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] }),
];
processes.forEach(proc => {
  proc.stdout.on('data', data => serverLog += data);
  proc.stderr.on('data', data => serverLog += data);
});
const report = { checks: [], pageErrors: [] };
let browser;
async function check(name, action) {
  try { report.checks.push({ name, passed: true, details: await action() }); }
  catch (error) { report.checks.push({ name, passed: false, error: error.message, at: error.stack?.split('\n')[1] }); }
}
async function waitReady(url) {
  for (let i = 0; i < 100; i++) {
    try { if ((await fetch(url)).ok) return; } catch {}
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  throw new Error(`Server unavailable ${url}: ${serverLog.slice(-1500)}`);
}
async function setup(page, beforeReply) {
  page.on('pageerror', error => report.pageErrors.push(error.message));
  await page.route('https://onecompiler.com/**', route => route.fulfill({ contentType: 'text/html', body: '<p>Editor placeholder</p>' }));
  await page.route(`${apiBase}/**`, async route => {
    const response = await route.fetch();
    if (beforeReply) await beforeReply(route.request(), response);
    await route.fulfill({ response, headers: { ...response.headers(), 'access-control-allow-origin': 'http://127.0.0.1:5188' } });
  });
  await page.goto('http://127.0.0.1:5188/', { waitUntil: 'domcontentloaded' });
}
async function openImport(page) {
  await page.locator('button[title^="Upload a Python file"]').click();
}
async function uploadFile(page, name, code) {
  await openImport(page);
  await page.getByRole('button', { name: /Python File \(.py\)/ }).click();
  const response = page.waitForResponse(r => r.url().endsWith('/api/projects/file'));
  await page.locator('#modalFileInput').setInputFiles({ name, mimeType: 'text/x-python', buffer: Buffer.from(code) });
  const result = await response;
  assert.equal(result.status(), 201);
  await page.getByRole('heading', { name: 'Import Project', exact: true }).waitFor({ state: 'hidden' });
  return result.json();
}
async function generate(page) {
  const response = page.waitForResponse(r => r.url().endsWith('/render'));
  await page.locator('.startButton').click();
  const result = await response;
  assert.equal(result.status(), 200);
  await page.locator('g[data-node-id]').first().waitFor();
  return result.json();
}
async function openExport(page) {
  await page.locator('button[title="Export Diagram (SVG, PNG, PDF)"]').click();
}

(async () => {
  try {
    await Promise.all([waitReady('http://127.0.0.1:8877/_browser_fixture'), waitReady('http://127.0.0.1:5188/')]);
    const executablePath = [process.env.FLOWBRIDGE_BROWSER_EXECUTABLE, chromium.executablePath(), 'C:/Program Files/Google/Chrome/Application/chrome.exe',
      'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(file => file && fs.existsSync(file));
    browser = await chromium.launch({ headless: true, executablePath });
    const page = await browser.newPage({ viewport: { width: 1500, height: 1000 }, acceptDownloads: true });
    page.setDefaultTimeout(7000);
    await setup(page);
    let project, rendered;
    await check('GitHub modal imports Python-only nested source using the real API', async () => {
      await openImport(page);
      await page.getByRole('button', { name: /GitHub Repo/ }).click();
      await page.getByPlaceholder('https://github.com/username/repository').fill('https://github.com/demo/repo');
      const response = page.waitForResponse(r => r.url().endsWith('/api/projects/github'));
      await page.getByRole('button', { name: 'Import from GitHub', exact: true }).click();
      const result = await response;
      assert.equal(result.status(), 201);
      project = await result.json();
      assert.equal(project.files.length, 3);
      assert.ok(project.files.some(f => f.filePath === 'tools/main.py'));
      assert.ok(project.files.find(f => f.filePath === 'app/main.py').fileContent.includes('café 😀"\r\n'));
      await page.getByRole('heading', { name: 'Import Project', exact: true }).waitFor({ state: 'hidden' });
      rendered = await generate(page);
      assert.ok(Object.keys(rendered.graphs).length >= 6);
      return { files: project.files.map(f => f.filePath), graphs: Object.keys(rendered.graphs).length };
    });
    await check('File drill-down shows edges and node-to-source / source-to-node highlighting', async () => {
      const file = rendered.flowchart.files.find(f => f.filePath === 'app/main.py');
      const ref = Object.entries(rendered.nodeToChildGraph).find(([, target]) => target === file.graphId);
      await page.locator(`g[data-node-id="${ref[0]}"]`).click();
      await page.locator('.sourceCodeScrollArea').getByText('message = "café 😀"', { exact: true }).waitFor();
      assert.ok(await page.locator('svg path.edge-line').count() > 0);
      const statement = rendered.flowchart.graphs[file.graphId].nodes.find(n => n.label.startsWith('message ='));
      await page.locator(`g[data-node-id="${statement.nodeId}"]`).click();
      await page.waitForFunction(id => document.getElementById(id)?.classList.contains('node-highlighted'), statement.nodeId);
      assert.equal(await page.locator(`g[data-node-id="${statement.nodeId}"]`).getAttribute('class'), 'node-highlighted');
      const line = page.locator('.sourceCodeScrollArea span[title^="Line 3:"]');
      assert.ok((await line.locator('..').getAttribute('style')).includes('255, 235, 59'));
      await line.click();
      assert.ok((await page.locator(`g[data-node-id="${statement.nodeId}"]`).getAttribute('class')).includes('node-highlighted'));
      return { edgeCount: await page.locator('svg path.edge-line').count(), sourceLine: 3 };
    });
    await check('Standalone viewer serves this project and supports drill-down', async () => {
      const viewer = await browser.newPage();
      viewer.on('pageerror', error => report.pageErrors.push(error.message));
      await viewer.goto(apiBase + rendered.viewerUrl);
      assert.equal(await viewer.locator('#levelIndicator').innerText(), 'PROJECT VIEW');
      await viewer.locator('#svgContainer g[data-target-graph]').first().click();
      assert.equal(await viewer.locator('#levelIndicator').innerText(), 'FILE VIEW');
      assert.ok(await viewer.locator('#svgContainer path.edge-line').count() > 0);
      await viewer.close();
    });
    await check('SVG export downloads the selected diagram', async () => {
      await openExport(page);
      const download = page.waitForEvent('download');
      await page.getByRole('button', { name: /SVG Vector Image/ }).click();
      const file = await download;
      await file.saveAs(path.join(output, 'browser-export.svg'));
      assert.ok(fs.readFileSync(path.join(output, 'browser-export.svg'), 'utf8').includes('<svg'));
      return file.suggestedFilename();
    });
    await check('PNG export downloads a nonempty PNG', async () => {
      await openExport(page);
      const download = page.waitForEvent('download');
      await page.getByRole('button', { name: /High-Res PNG Image/ }).click();
      const file = await download;
      await file.saveAs(path.join(output, 'browser-export.png'));
      const bytes = fs.readFileSync(path.join(output, 'browser-export.png'));
      assert.equal(bytes.subarray(1, 4).toString(), 'PNG');
      return { name: file.suggestedFilename(), bytes: bytes.length };
    });
    await check('PDF export opens a printable diagram page', async () => {
      await page.evaluate(() => {
        const open = window.open.bind(window);
        window.open = (...args) => {
          const popup = open(...args);
          if (popup) popup.print = () => { popup.reviewPrintCalled = true; };
          return popup;
        };
      });
      await openExport(page);
      const popupPromise = page.waitForEvent('popup');
      await page.getByRole('button', { name: /PDF/ }).click();
      const popup = await popupPromise;
      await popup.locator('svg').waitFor();
      await popup.waitForFunction(() => window.reviewPrintCalled === true);
      await popup.pdf({ path: path.join(output, 'browser-print-preview.pdf'), landscape: true });
      await popup.close();
      return 'Print-page wiring and headless PDF rendering verified; no native print dialog tested.';
    });
    await check('Cross-file function drill-down shows its function and source', async () => {
      const helper = rendered.flowchart.functions.find(fn => fn.functionName === 'adjust');
      const currentFile = rendered.flowchart.files.find(f => f.filePath === 'app/main.py');
      const node = rendered.flowchart.graphs[currentFile.graphId].nodes.find(n => rendered.nodeToChildGraph[n.nodeId] === helper.graphId);
      await page.locator(`g[data-node-id="${node.nodeId}"]`).click();
      await page.locator('.sourceCodeScrollArea').getByText('    if value > 0:', { exact: true }).waitFor();
      assert.ok(await page.locator('svg path.edge-line').count() > 0);
      return { edgeCount: await page.locator('svg path.edge-line').count() };
    });
    await check('Selecting duplicate basenames from the file list shows the correct source', async () => {
      await page.getByRole('button', { name: /All Files/ }).click();
      const toolsIndex = project.files.findIndex(f => f.filePath === 'tools/main.py');
      await page.locator('.sourceCodeScrollArea > div').nth(toolsIndex).click();
      const source = await page.locator('.sourceCodeScrollArea').innerText();
      assert.ok(source.includes('def tool()'), `tools/main.py selected but source reads: ${source}`);
      return source;
    });
    await check('Failed GitHub imports preserve the current project', async () => {
      const oldSource = await page.locator('.sourceCodeScrollArea').innerText();
      await openImport(page);
      await page.getByRole('button', { name: /GitHub Repo/ }).click();
      await page.getByPlaceholder('https://github.com/username/repository').fill('https://github.com/demo/missing');
      const response = page.waitForResponse(r => r.url().endsWith('/api/projects/github'));
      await page.getByRole('button', { name: 'Import from GitHub', exact: true }).click();
      assert.equal((await response).status(), 502);
      await page.getByText(/not found|not accessible|public|accessible/i).last().waitFor();
      assert.equal(await page.locator('.sourceCodeScrollArea').innerText(), oldSource);
      await page.getByRole('heading', { name: 'Import Project', exact: true }).locator('..').locator('..').getByRole('button', { name: '✕' }).click();
    });
    await check('Regular Python uploads generate a diagram', async () => {
      await uploadFile(page, 'regular.py', 'answer = 42\n');
      await generate(page);
      assert.ok(await page.locator('g[data-node-id]').count() > 0);
    });
    await check('ZIP uploads use the same nested Python filtering', async () => {
      const zip = Buffer.from(await (await fetch('http://127.0.0.1:8877/_browser_fixture/archive.zip')).arrayBuffer());
      await openImport(page);
      await page.getByRole('button', { name: /ZIP Project|ZIP Archive|ZIP File/ }).click();
      const response = page.waitForResponse(r => r.url().endsWith('/api/projects/zip'));
      await page.locator('#modalZipInput').setInputFiles({ name: 'project.zip', mimeType: 'application/zip', buffer: zip });
      const result = await response;
      assert.equal(result.status(), 201);
      assert.equal((await result.json()).files.length, 3);
      await page.getByRole('heading', { name: 'Import Project', exact: true }).waitFor({ state: 'hidden' });
      await generate(page);
    });
    await check('Invalid Python is shown with a syntax diagnostic', async () => {
      await uploadFile(page, 'broken.py', 'def broken(:\n');
      const data = await generate(page);
      assert.equal(data.analysisStatus, 'partial');
      const ref = Object.entries(data.nodeToChildGraph).find(([, target]) => target === data.flowchart.files[0].graphId);
      await page.locator(`g[data-node-id="${ref[0]}"]`).click();
      await page.getByText('Syntax Error', { exact: true }).first().waitFor();
    });
    await check('A finished old render cannot replace the newly uploaded project', async () => {
      const race = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
      race.setDefaultTimeout(7000);
      let release, started;
      const gate = new Promise(resolve => release = resolve);
      const pending = new Promise(resolve => started = resolve);
      await setup(race, async request => {
        if (request.url().endsWith('/render')) { started(); await gate; }
      });
      await uploadFile(race, 'old.py', 'old_value = 1\n');
      await race.locator('.startButton').click();
      await pending;
      await uploadFile(race, 'new.py', 'new_value = 2\n');
      release();
      await race.getByTitle('Generate Flowchart', {exact: true}).waitFor();
      await race.waitForTimeout(150);
      const state = await race.locator('main').innerText();
      assert.ok(!state.includes('old.py'), `Old render appears after new.py uploaded: ${state}`);
      await race.close();
    });
    await page.screenshot({ path: path.join(output, 'final-ui.png') });
    assert.deepEqual(report.pageErrors, []);
  } catch (error) {
    report.fatal = error.stack;
  } finally {
    if (browser) await browser.close();
    for (const child of processes) {
      if (child.exitCode === null) {
        const exited = once(child, 'exit');
        child.kill();
        await Promise.race([exited, new Promise(resolve => setTimeout(resolve, 2000))]);
      }
    }
    fs.writeFileSync(path.join(artifacts, 'browser-last.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
    process.exitCode = report.fatal || report.checks.some(item => !item.passed) ? 1 : 0;
    const target = path.resolve(output);
    if (target.startsWith(path.resolve(artifacts) + path.sep) && path.basename(target).startsWith('run-')) {
      fs.rmSync(target, {recursive: true, force: true, maxRetries: 3, retryDelay: 100});
    }
  }
})();
