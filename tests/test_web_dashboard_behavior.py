import json
from pathlib import Path
import shutil
import subprocess
import textwrap
import unittest


WEB_INDEX = Path(__file__).resolve().parents[1] / "gui" / "web" / "index.html"
NODE = shutil.which("node")


NODE_HARNESS = r"""
const fs = require('fs');
const vm = require('vm');

const htmlPath = process.argv[1];
const scenario = process.argv[2];
const html = fs.readFileSync(htmlPath, 'utf8');
const match = html.match(/<script>([\s\S]*?)<\/script>/);
if (!match) throw new Error('inline dashboard script not found');

class FakeClassList {
  constructor(initial = '') {
    this.values = new Set(String(initial).split(/\s+/).filter(Boolean));
  }
  add(...names) { names.forEach(name => this.values.add(name)); }
  remove(...names) { names.forEach(name => this.values.delete(name)); }
  contains(name) { return this.values.has(name); }
  toggle(name, force) {
    const next = force === undefined ? !this.values.has(name) : !!force;
    if (next) this.values.add(name); else this.values.delete(name);
    return next;
  }
  toString() { return [...this.values].join(' '); }
}

const elements = new Map();
const detailsIds = new Set([
  'diagnostic-evidence',
  'ai-disclosure',
  'technical-log-details',
]);
const buttonIds = new Set([
  'dashboard-primary-button',
  'btn-diagnose',
  'btn-open-proxy',
  'btn-open-ai',
  'btn-open-logs',
]);

class FakeElement {
  constructor(id = '', tagName = 'DIV') {
    this.id = id;
    this.tagName = tagName;
    this.classList = new FakeClassList();
    this.style = {};
    this.dataset = {};
    this.attributes = {};
    this.listeners = {};
    this.children = [];
    this._innerHTML = '';
    this.textContent = '';
    this.value = '';
    this.checked = false;
    this.disabled = false;
    this.hidden = false;
    this.open = false;
    this.scrollTop = 0;
    this.scrollHeight = 0;
  }
  set innerHTML(value) {
    this._innerHTML = String(value ?? '');
    if (this._innerHTML.includes('data-dashboard-primary-action')) {
      const child = getElement('dashboard-primary-button', 'BUTTON');
      const action = this._innerHTML.match(/data-dashboard-primary-action="([^"]*)"/);
      const target = this._innerHTML.match(/data-dashboard-primary-target="([^"]*)"/);
      child.dataset.dashboardPrimaryAction = action ? action[1] : '';
      child.dataset.dashboardPrimaryTarget = target ? target[1] : '';
      child.disabled = /<button[^>]*\sdisabled(?:\s|>)/.test(this._innerHTML);
    }
  }
  get innerHTML() { return this._innerHTML; }
  set className(value) { this.classList = new FakeClassList(value); }
  get className() { return this.classList.toString(); }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name === 'open') this.open = true;
    if (name === 'hidden') this.hidden = true;
    if (name.startsWith('data-')) {
      const key = name.slice(5).replace(/-([a-z])/g, (_, char) => char.toUpperCase());
      this.dataset[key] = String(value);
    }
  }
  removeAttribute(name) {
    delete this.attributes[name];
    if (name === 'open') this.open = false;
    if (name === 'hidden') this.hidden = false;
  }
  getAttribute(name) {
    if (name === 'data-section') return this.dataset.section || null;
    return this.attributes[name] ?? null;
  }
  addEventListener(type, listener) {
    (this.listeners[type] ||= []).push(listener);
  }
  dispatch(type) {
    for (const listener of this.listeners[type] || []) listener({ type, target: this });
    const inline = this['on' + type];
    if (typeof inline === 'function') inline({ type, target: this });
  }
  querySelector(selector) {
    if (selector === '[data-dashboard-primary-action]') return getElement('dashboard-primary-button', 'BUTTON');
    if (selector === '.card-value') return getElement(this.id + '-card-value');
    if (selector === 'h3' || selector === '[data-panel-heading]') return getElement(this.id + '-heading', 'H3');
    if (selector === 'summary') return getElement(this.id + '-summary', 'SUMMARY');
    return null;
  }
  querySelectorAll() { return []; }
  scrollIntoView() {}
  focus() { document.activeElement = this; }
}

function inferredTag(id) {
  if (detailsIds.has(id)) return 'DETAILS';
  if (buttonIds.has(id)) return 'BUTTON';
  return 'DIV';
}

function getElement(id, tagName = null) {
  if (!elements.has(id)) elements.set(id, new FakeElement(id, tagName || inferredTag(id)));
  const element = elements.get(id);
  if (tagName) element.tagName = tagName;
  return element;
}

const sectionIds = {
  current_status: 'home-panel',
  connection_quality: 'connection-quality',
  diagnostic_evidence: 'diagnostic-evidence',
  latest_result: 'latest-result',
  ai: 'ai-disclosure',
  logs: 'log-panel',
};
for (const [section, id] of Object.entries(sectionIds)) {
  getElement(id).dataset.section = section;
}
getElement('proxy-panel').classList.add('hidden');
getElement('ai-panel').classList.add('hidden');
getElement('log-panel').classList.add('hidden');
getElement('btn-diagnose', 'BUTTON').classList.add('hidden');
getElement('dashboard-primary-button', 'BUTTON').disabled = true;

const document = {
  body: getElement('body', 'BODY'),
  activeElement: null,
  getElementById: id => getElement(id),
  querySelector: selector => {
    if (selector === 'input[name="diagnose-goal"]:checked') return null;
    return null;
  },
  querySelectorAll: selector => {
    if (selector === '[data-section]') return Object.values(sectionIds).map(id => getElement(id));
    return [];
  },
  createElement: tag => new FakeElement('', String(tag).toUpperCase()),
};

const calls = [];
let runRelease = null;
let holdRun = false;
let dashboardRelease = null;
let holdDashboard = false;
let failDashboard = false;
const response = (data, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => data,
});

const dashboardState = {
  schema_version: 'netfix_current_mac_state.v2',
  decision: {
    effective_route: 'none',
    primary_action: 'paste_proxy',
    requires_confirmation: false,
  },
  verdict: {
    status: 'unknown',
    severity: 'info',
    headline: '还没有粘贴代理参数',
    detail: '当前没有保存或启用的代理。',
    next_step: '粘贴已有线路后再检查。',
    primary_action: {
      id: 'paste_proxy',
      label: '粘贴代理参数',
      enabled: true,
      target: 'flow:proxy_setup',
      requires_confirmation: false,
    },
  },
  presentation: {
    visible_sections: ['current_status', 'connection_quality'],
    collapsed_sections: ['diagnostic_evidence'],
    suppressed_sections: [
      { id: 'ai', reason: 'optional_support' },
      { id: 'logs', reason: 'history_only' },
      { id: 'diagnose_goals', reason: 'not_current_scope' },
    ],
  },
  connection_quality: {
    collection_state: 'not_run',
    status: 'unchecked',
    headline: '还没有体感数据',
    detail: '运行检查后会显示速度、延迟和稳定性。',
  },
  machine: { primary_interface: 'en0', self_ipv4: '192.168.1.25' },
  proxy: { system: { active: false }, saved: { count: 0 } },
  egress: { status: 'unchecked' },
};

async function fetch(url, options = {}) {
  const path = String(url);
  const body = options.body ? JSON.parse(options.body) : null;
  calls.push({ method: options.method || 'GET', path, body });
  if (path === '/run' && holdRun) {
    return new Promise(resolve => { runRelease = () => resolve(response({ ok: false, error: 'released test job' }, 400)); });
  }
  if (path === '/dashboard/state' && holdDashboard) {
    return new Promise(resolve => { dashboardRelease = () => resolve(response(dashboardState)); });
  }
  if (path === '/dashboard/state' && failDashboard) {
    return response({ ok: false, error: 'dashboard unavailable' }, 503);
  }
  if (path === '/proxy/validate') {
    if (String(body?.input || '').includes('bad.example')) {
      return response({ ok: false, error: 'connection_refused', proxy_check: { status: 'fail', error: 'connection_refused' } }, 400);
    }
    return response({
      ok: true,
      validation_receipt: 'receipt-for-current-input',
      proxy_check: { tcp: 'ok', auth: 'ok', http_code: 204, latency_ms: 45 },
    });
  }
  if (path === '/proxy/profiles' && (options.method || 'GET') === 'POST') {
    return response({ ok: true, profile: { id: 'saved-profile', can_apply: true } });
  }
  const payloads = {
    '/health': { ok: true, version: 'test' },
    '/dashboard/state': dashboardState,
    '/run': { ok: false, error: 'stop after request capture' },
    '/proxy/validation-targets': { ok: true, profiles: [] },
    '/proxy/profiles': { ok: true, profiles: [] },
    '/proxy/bridge': { ok: true, bridges: [], stale_check: {} },
    '/proxy/monitor': { ok: true, monitor: {} },
    '/settings/proxy-bridge': { ok: true, settings: {} },
    '/proxy/bridge/recover': { ok: true, status: 'recovered' },
    '/llm/providers': { ok: true, providers: [] },
    '/settings/llm': { ok: true, settings: { enabled: false, fallback: {}, budget: {}, features: {} } },
    '/llm/chain-readiness': { ok: true, chains: [] },
    '/logs': { ok: true, latest_report_exists: false, events: [] },
    '/settings/privacy': { ok: true, settings: {} },
    '/data/clear': { ok: true, keychain: { deleted: [] }, llm_budget: { removed: [] } },
  };
  return response(payloads[path] || { ok: true });
}

const context = {
  console,
  document,
  window: { location: { protocol: 'http:' } },
  navigator: { clipboard: { writeText: async () => {} } },
  fetch,
  confirm: () => true,
  FileReader: class {},
  Date,
  Promise,
  Set,
  Map,
  JSON,
  Math,
  Number,
  String,
  Array,
  Object,
  RegExp,
  Error,
  setTimeout: (fn) => { Promise.resolve().then(fn); return 1; },
  clearTimeout: () => {},
};
context.globalThis = context;
vm.createContext(context);

let script = match[1].replace(/\n\s*boot\(\);\s*$/, '\n');
script += `
globalThis.__dashboardTest = {
  boot,
  renderDashboardState,
  renderSectionByPresentation,
  primaryActionFromVerdict,
  runDashboardPrimaryAction,
  runDiagnose,
  openProxyPanel,
  openAIPanel,
  openLogs,
  clearAllData,
  loadDashboardState,
  log,
  validateProxy,
  saveProxyProfile,
  normalizePrimaryTarget: typeof normalizePrimaryTarget === 'function' ? normalizePrimaryTarget : null,
  replayLogBuffer: typeof replayLogBuffer === 'function' ? replayLogBuffer : null,
  get operationInProgress() { return operationInProgress; },
};`;
vm.runInContext(script, context, { filename: htmlPath });
const api = context.__dashboardTest;
const flush = async (turns = 8) => {
  for (let i = 0; i < turns; i += 1) await Promise.resolve();
};
const count = path => calls.filter(call => call.path === path).length;
const assert = (condition, message) => {
  if (!condition) throw new Error(message);
};

async function runScenario() {
  if (scenario === 'boot') {
    await api.boot();
    assert(JSON.stringify(calls.map(call => call.path).sort()) === JSON.stringify(['/dashboard/state', '/health']), `unexpected boot calls: ${JSON.stringify(calls)}`);
    return { calls };
  }

  if (scenario === 'loading-neutral') {
    getElement('status-dot').className = 'status-dot neutral';
    getElement('status-text').textContent = '正在连接本地服务';
    holdDashboard = true;
    const pendingBoot = api.boot();
    await flush();
    assert(count('/health') === 1 && count('/dashboard/state') === 1, 'boot did not start both home requests');
    assert(getElement('status-dot').classList.contains('neutral'), `health resolved before state and changed status to ${getElement('status-dot').className}`);
    assert(getElement('dashboard-primary-button').disabled === true, 'primary action enabled before dashboard state resolved');
    dashboardRelease();
    await pendingBoot;
    return { status: getElement('status-dot').className };
  }

  if (scenario === 'presentation') {
    api.renderDashboardState(dashboardState);
    const evidence = getElement('diagnostic-evidence');
    const ai = getElement('ai-disclosure');
    const logs = getElement('log-panel');
    assert(evidence.tagName === 'DETAILS', 'collapsed diagnostic evidence is not a details element');
    assert(evidence.dataset.presentationState === 'collapsed', `diagnostic state=${evidence.dataset.presentationState}`);
    assert(evidence.hidden === false && evidence.open === false, 'collapsed diagnostic evidence must be present and closed');
    assert(ai.dataset.presentationState === 'suppressed' && ai.hidden === true, 'suppressed AI must be hidden');
    assert(logs.dataset.presentationState === 'suppressed' && logs.hidden === true, 'suppressed logs must be hidden');

    const visible = JSON.parse(JSON.stringify(dashboardState));
    visible.presentation.visible_sections.push('diagnostic_evidence');
    visible.presentation.collapsed_sections = [];
    api.renderDashboardState(visible);
    assert(evidence.dataset.presentationState === 'visible' && evidence.open === true, 'visible details section must be open');
    return { evidence: evidence.dataset, ai: ai.dataset, logs: logs.dataset };
  }

  if (scenario === 'targets') {
    assert(api.normalizePrimaryTarget, 'normalizePrimaryTarget is not exposed');
    assert(api.normalizePrimaryTarget({ id: 'paste_proxy', target: 'flow:proxy_setup' }) === 'flow:proxy_setup', 'canonical proxy flow not supported');
    assert(api.normalizePrimaryTarget({ id: 'paste_proxy', target: 'settings:proxy' }) === 'flow:proxy_setup', 'legacy proxy alias not supported');
    assert(api.normalizePrimaryTarget({ id: 'recover_system_proxy', target: 'recover:stale_bridge' }) === 'recover:stale_bridge', 'canonical recovery target not supported');
    assert(api.normalizePrimaryTarget({ id: 'recover_system_proxy', target: 'recover:system_proxy' }) === 'recover:stale_bridge', 'legacy recovery alias not supported');
    assert(api.normalizePrimaryTarget({ id: 'none', target: 'none' }) === 'none', 'none target not supported');
    const beforeNone = calls.length;
    await api.runDashboardPrimaryAction({ id: 'none', target: 'none', label: '无需操作', enabled: false });
    assert(calls.length === beforeNone, 'none target triggered a request');
    await api.runDashboardPrimaryAction({ id: 'paste_proxy', target: 'flow:proxy_setup', label: '粘贴代理参数', enabled: true });
    assert(!getElement('proxy-panel').classList.contains('hidden'), 'proxy flow did not open proxy setup');
    return { calls };
  }

  if (scenario === 'doctor') {
    await api.runDashboardPrimaryAction({ id: 'diagnose', target: 'run:doctor', label: '检查当前网络', enabled: true });
    await flush();
    const run = calls.find(call => call.path === '/run');
    assert(run, 'doctor action did not POST /run');
    assert(JSON.stringify(run.body.command) === JSON.stringify(['doctor']), `doctor command was ${JSON.stringify(run.body.command)}`);
    return run;
  }

  if (scenario === 'recovery') {
    await api.runDashboardPrimaryAction({ id: 'recover_system_proxy', target: 'recover:stale_bridge', label: '恢复原来的网络设置', enabled: true });
    await flush();
    const recover = calls.find(call => call.path === '/proxy/bridge/recover');
    assert(recover, 'recovery target did not call bridge recovery endpoint');
    assert(recover.body.confirmed === true, 'recovery confirmation flag missing');
    assert(recover.body.confirmation === 'RESTORE_STALE_PROXY_BRIDGE', `wrong recovery confirmation: ${JSON.stringify(recover.body)}`);
    return recover;
  }

  if (scenario === 'lock') {
    holdRun = true;
    const first = api.runDiagnose();
    const second = api.runDiagnose();
    await flush();
    assert(count('/run') === 1, `single-job lock allowed ${count('/run')} POST /run calls`);
    assert(getElement('dashboard-primary-button').disabled === true, 'primary button was not disabled while job was active');
    runRelease();
    await Promise.all([first, second]);
    assert(api.operationInProgress === false, 'operation lock did not release');
    return { runCalls: count('/run') };
  }

  if (scenario === 'lazy') {
    await api.boot();
    api.openAIPanel();
    api.openAIPanel();
    api.openProxyPanel();
    api.openProxyPanel();
    api.openLogs();
    api.openLogs();
    await flush(30);
    assert(count('/llm/providers') === 1, `AI providers loaded ${count('/llm/providers')} times`);
    assert(count('/settings/llm') === 1, `AI settings loaded ${count('/settings/llm')} times`);
    assert(count('/proxy/validation-targets') === 1, `proxy targets loaded ${count('/proxy/validation-targets')} times`);
    assert(count('/proxy/profiles') === 1, `proxy profiles loaded ${count('/proxy/profiles')} times`);
    assert(count('/proxy/bridge') === 1, `proxy bridge loaded ${count('/proxy/bridge')} times`);
    assert(count('/proxy/monitor') === 1, `proxy monitor loaded ${count('/proxy/monitor')} times`);
    assert(count('/settings/proxy-bridge') === 1, `proxy settings loaded ${count('/settings/proxy-bridge')} times`);
    assert(count('/logs') === 1, `logs loaded ${count('/logs')} times`);
    assert(count('/settings/privacy') === 1, `privacy settings loaded ${count('/settings/privacy')} times`);
    return { calls };
  }

  if (scenario === 'clear-data') {
    await api.clearAllData();
    await flush(20);
    const aiCalls = calls.filter(call => call.path.startsWith('/llm/') || call.path === '/settings/llm');
    assert(aiCalls.length === 0, `clear data pulled AI endpoints: ${JSON.stringify(aiCalls)}`);
    return { calls };
  }

  if (scenario === 'log-buffer') {
    const technical = getElement('technical-log-details');
    const target = getElement('log');
    api.log('buffered-before-open');
    assert(target.textContent === '', `closed log disclosure rendered early: ${target.textContent}`);
    assert(api.replayLogBuffer, 'replayLogBuffer is not exposed');
    technical.open = true;
    api.replayLogBuffer();
    assert(target.textContent.includes('buffered-before-open'), 'opening log disclosure did not replay buffered entry');
    technical.open = false;
    api.log('buffered-while-closed');
    assert(!target.textContent.includes('buffered-while-closed'), 'closed disclosure rendered a new entry');
    technical.open = true;
    api.replayLogBuffer();
    assert(target.textContent.includes('buffered-while-closed'), 'second open did not replay complete buffer');
    return { text: target.textContent };
  }

  if (scenario === 'home-privacy') {
    const state = JSON.parse(JSON.stringify(dashboardState));
    state.decision.effective_route = 'external_system_proxy';
    state.proxy.system = { active: true, kind: 'http_https' };
    state.egress = {
      public_ipv4: '203.0.113.7',
      public_ipv4_hash: 'hash-secret',
      base_rtt: '41ms',
      status: 'ok',
    };
    api.renderDashboardState(state);
    const home = getElement('current-mac-state').innerHTML + getElement('dashboard-next-action').innerHTML + getElement('dashboard-headline').textContent + getElement('dashboard-impact').textContent;
    for (const forbidden of ['203.0.113.7', 'hash-secret', '41ms', '外部系统代理', 'API Key', '一键诊断', 'en0']) {
      assert(!home.includes(forbidden), `ordinary home leaked forbidden value: ${forbidden}`);
    }
    return { home };
  }

  if (scenario === 'focus') {
    api.openProxyPanel();
    await flush();
    assert(document.activeElement && document.activeElement.id === 'proxy-panel-heading', `proxy panel focus was ${document.activeElement && document.activeElement.id}`);
    return { active: document.activeElement.id };
  }

  if (scenario === 'dashboard-error') {
    failDashboard = true;
    await api.loadDashboardState();
    const button = getElement('dashboard-primary-button');
    assert(button.textContent === '重新读取', `error CTA was ${button.textContent}`);
    assert(button.disabled === false, 'error CTA stayed disabled');
    assert(!getElement('btn-open-proxy').classList.contains('hidden'), 'proxy entry hidden during dashboard error');
    assert(!getElement('btn-open-logs').classList.contains('hidden'), 'logs entry hidden during dashboard error');
    failDashboard = false;
    const before = count('/dashboard/state');
    await api.runDashboardPrimaryAction();
    assert(count('/dashboard/state') === before + 1, 'retry CTA did not reread dashboard state');
    return { calls };
  }

  if (scenario === 'proxy-receipt') {
    getElement('proxy-input').value = 'http://user:pass@proxy.example:8000';
    getElement('proxy-target-profile').value = 'ai_dev';
    getElement('proxy-start-monitor-on-save').checked = false;
    await api.saveProxyProfile();
    await flush(20);
    const validateIndex = calls.findIndex(call => call.path === '/proxy/validate');
    const saveIndex = calls.findIndex(call => call.path === '/proxy/profiles' && call.method === 'POST');
    assert(validateIndex >= 0, 'save did not synchronously validate first');
    assert(saveIndex > validateIndex, 'profile was saved before validation completed');
    const save = calls[saveIndex];
    assert(save.body.validation_receipt === 'receipt-for-current-input', `save receipt missing: ${JSON.stringify(save.body)}`);
    assert(save.body.target_profile === 'ai_dev', `save target mismatch: ${JSON.stringify(save.body)}`);
    return { calls };
  }

  if (scenario === 'proxy-preflight-fail') {
    getElement('proxy-input').value = 'http://user:pass@bad.example:8000';
    getElement('proxy-target-profile').value = 'baseline';
    await api.saveProxyProfile();
    await flush(20);
    assert(count('/proxy/validate') === 1, 'failed save did not run preflight');
    const saves = calls.filter(call => call.path === '/proxy/profiles' && call.method === 'POST');
    assert(saves.length === 0, `failed preflight still saved ${saves.length} profiles`);
    assert(getElement('proxy-result').innerHTML.includes('没有保存'), 'failed preflight did not explain that nothing was saved');
    return { calls };
  }

  throw new Error(`unknown scenario: ${scenario}`);
}

runScenario()
  .then(result => process.stdout.write(JSON.stringify(result)))
  .catch(error => {
    process.stderr.write(String(error && error.stack || error));
    process.exitCode = 1;
  });
"""


@unittest.skipUnless(NODE, "Node.js is required for executable Web behavior tests")
class TestWebDashboardBehavior(unittest.TestCase):
    maxDiff = None

    def run_scenario(self, scenario: str) -> dict:
        completed = subprocess.run(
            [NODE, "-e", NODE_HARNESS, str(WEB_INDEX), scenario],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=f"Node scenario {scenario!r} failed:\n{completed.stderr}\n{completed.stdout}",
        )
        return json.loads(completed.stdout or "{}")

    def test_home_shell_is_neutral_semantic_and_single_column(self):
        html = WEB_INDEX.read_text(encoding="utf-8")
        home = html[html.index('id="home-panel"'):html.index('id="recovery-panel"')]

        self.assertIn('class="status-dot neutral"', html)
        self.assertIn('role="status"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn('id="dashboard-headline"', home)
        self.assertIn('id="dashboard-impact"', home)
        self.assertIn('id="dashboard-primary-button"', home)
        self.assertIn('aria-describedby="dashboard-impact"', home)
        self.assertIn('id="dashboard-primary-button"', home)
        self.assertIn("disabled", home)
        self.assertNotIn("<aside", html)
        self.assertNotIn('id="assist-panel"', html)
        self.assertNotIn('id="diagnose-goals"', home)
        self.assertIn(':focus-visible', html)

    def test_boot_consumes_only_health_and_dashboard_state(self):
        self.run_scenario("boot")

    def test_loading_stays_neutral_until_both_home_requests_finish(self):
        self.run_scenario("loading-neutral")

    def test_presentation_states_control_real_disclosures(self):
        self.run_scenario("presentation")

    def test_canonical_targets_and_legacy_aliases_are_normalized(self):
        self.run_scenario("targets")

    def test_doctor_target_posts_doctor_command(self):
        self.run_scenario("doctor")

    def test_recovery_target_uses_confirmed_bridge_endpoint(self):
        self.run_scenario("recovery")

    def test_primary_action_has_single_job_lock(self):
        self.run_scenario("lock")

    def test_optional_panels_are_lazy_and_deduplicated(self):
        self.run_scenario("lazy")

    def test_clear_data_does_not_pull_ai_state(self):
        self.run_scenario("clear-data")

    def test_runtime_log_is_buffered_until_disclosure_opens(self):
        self.run_scenario("log-buffer")

    def test_home_does_not_render_sensitive_or_technical_identity_fields(self):
        self.run_scenario("home-privacy")

    def test_opened_panel_receives_focus(self):
        self.run_scenario("focus")

    def test_dashboard_error_keeps_tools_and_exposes_retry_action(self):
        self.run_scenario("dashboard-error")

    def test_proxy_save_requires_matching_preflight_receipt(self):
        self.run_scenario("proxy-receipt")

    def test_proxy_preflight_failure_never_saves(self):
        self.run_scenario("proxy-preflight-fail")

    def test_responsive_contract_includes_required_viewport_breakpoints(self):
        html = WEB_INDEX.read_text(encoding="utf-8")
        css = html[html.index("<style>"):html.index("</style>")]
        self.assertIn("@media (max-width: 480px)", css)
        self.assertIn("@media (max-width: 375px)", css)
        self.assertIn("min-width: 0", css)
        self.assertIn("overflow-wrap: anywhere", css)
        self.assertNotIn("min-width: 320px", css)

    def test_quality_fallback_is_honest_and_home_has_no_helper_slogan(self):
        html = WEB_INDEX.read_text(encoding="utf-8")
        self.assertNotIn("本次检查会补上", html)
        self.assertIn('<div class="headline">网络体感</div>', html)
        self.assertNotIn("q.headline || '网络体感'", html)
        nav = html[html.index('<nav class="secondary-tools"'):html.index('</nav>', html.index('<nav class="secondary-tools"'))]
        self.assertNotIn("需要时再用", nav)


if __name__ == "__main__":
    unittest.main()
