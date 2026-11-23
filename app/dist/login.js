/* Django session login for the local geoSys frontend. */
(function () {
  'use strict';
  var form = document.getElementById('login-form');
  var fallback = document.getElementById('login-feedback');
  var messageTimer;
  var submitting = false;

  function showMessage(message) {
    var layer = window.layer || (window.layui && window.layui.layer);
    if (layer) {
      layer.msg(message, { icon: 5, time: 2000, shift: 6 });
      return;
    }
    clearTimeout(messageTimer);
    fallback.textContent = message;
    fallback.hidden = false;
    messageTimer = setTimeout(function () { fallback.hidden = true; }, 2000);
  }

  function ensureCsrf() {
    if (!window.GeoAPI) return Promise.resolve();
    if (window.GeoAPI.csrfToken()) return Promise.resolve();
    return window.GeoAPI.request('/api/auth/csrf');
  }

  function submitLogin(event) {
    event.preventDefault();
    if (submitting) return;
    if (!document.getElementById('agree_input').checked) {
      showMessage('请阅读并勾选用户协议');
      return;
    }
    if (!window.GeoAPI) {
      showMessage('登录接口未加载，请通过 Django 服务访问页面');
      return;
    }

    var username = document.getElementById('username').value.trim();
    var password = document.getElementById('password').value;
    var keeplogin = !!(document.getElementById('keeplogin') && document.getElementById('keeplogin').checked);
    if (!username || !password) {
      showMessage('请输入账号和密码');
      return;
    }

    submitting = true;
    ensureCsrf().then(function () {
      return window.GeoAPI.login({ username: username, password: password, keeplogin: keeplogin });
    }).then(function (result) {
      if (!result.ok) {
        showMessage((result.error && result.error.message) || '登录失败');
        return;
      }
      try {
        sessionStorage.setItem('geo-demo-session', 'active');
        if (keeplogin) localStorage.setItem('geo-demo-remember', 'active');
        else localStorage.removeItem('geo-demo-remember');
      } catch (error) { /* session cookie is authoritative */ }
      window.location.assign('/user/index/index');
    }).catch(function () {
      showMessage('无法连接登录服务，请确认后端已启动');
    }).finally(function () {
      submitting = false;
    });
  }

  if (window.jQuery) {
    window.jQuery(form).on('submit', submitLogin);
  } else {
    form.addEventListener('submit', submitLogin);
  }
}());
