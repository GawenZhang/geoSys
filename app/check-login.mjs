import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

const loginHtml = await readFile(new URL('login.html', import.meta.url), 'utf8');
const loginCode = await readFile(new URL('login.js', import.meta.url), 'utf8');
let checks = 0;
async function verify(description, action) {
  await action();
  checks += 1;
  console.log('PASS ' + description);
}
function storage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: key => values.delete(key)
  };
}
function environment(session = {}, remembered = {}) {
  const events = {};
  const nodes = {};
  for (const id of ['login-form', 'login-feedback', 'username', 'password', 'agree_input', 'keeplogin', 'demo-content', 'logout']) {
    nodes[id] = { value: '', checked: false, hidden: true, addEventListener: (name, callback) => { events[id + ':' + name] = callback; } };
  }
  nodes.agree_input.checked = true;
  const destinations = [];
  const messages = [];
  const context = {
    document: { getElementById: id => nodes[id] },
    sessionStorage: storage(session),
    localStorage: storage(remembered),
    window: { location: { assign: url => destinations.push(url), replace: url => destinations.push(url) }, layer: { msg: text => messages.push(text) } },
    setTimeout, clearTimeout
  };
  context.window.GeoAPI = {
    csrfToken: () => 'test-token',
    login: async ({ username, password }) => username === 'demo' && password === 'demo123'
      ? { ok: true }
      : { ok: false, error: { message: '账号或密码错误' } }
  };
  vm.createContext(context);
  return { context, nodes, events, destinations, messages };
}
function runLogin() {
  const env = environment();
  vm.runInContext(loginCode, env.context);
  env.submit = async () => {
    env.events['login-form:submit']({ preventDefault() {} });
    await new Promise(resolve => setImmediate(resolve));
  };
  return env;
}

await verify('both empty fields declare native required validation (HTML only)', () => {
  for (const id of ['username', 'password']) {
    const input = loginHtml.match(new RegExp('<input\\b[^>]*id="' + id + '"[^>]*>'))?.[0];
    assert.ok(input && /\brequired\b/.test(input));
  }
});
await verify('login page does not redirect automatically', () => assert.equal(runLogin().destinations.length, 0));
await verify('unchecked agreement blocks the local submission', async () => {
  const env = runLogin();
  env.nodes.agree_input.checked = false;
  await env.submit();
  assert.equal(env.messages[0], '请阅读并勾选用户协议');
  assert.equal(env.destinations.length, 0);
});
await verify('incorrect credentials display the authentication error', async () => {
  const env = runLogin();
  env.nodes.username.value = 'invalid';
  env.nodes.password.value = 'invalid';
  await env.submit();
  assert.equal(env.messages[0], '账号或密码错误');
  assert.equal(env.destinations.length, 0);
});
await verify('successful login stores a marker and opens the admin shell', async () => {
  const env = runLogin();
  env.nodes.username.value = 'demo';
  env.nodes.password.value = 'demo123';
  await env.submit();
  assert.equal(env.context.sessionStorage.getItem('geo-demo-session'), 'active');
  assert.equal(env.context.localStorage.getItem('geo-demo-remember'), null);
  assert.deepEqual(env.destinations, ['/user/index/index']);
});
await verify('remember option persists a marker without storing a password', async () => {
  const env = runLogin();
  env.nodes.username.value = 'demo';
  env.nodes.password.value = 'demo123';
  env.nodes.keeplogin.checked = true;
  await env.submit();
  assert.equal(env.context.localStorage.getItem('geo-demo-remember'), 'active');
});
console.log(checks + ' logic/HTML checks passed. These are not browser or visual checks.');

