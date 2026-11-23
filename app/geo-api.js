/* Shared fetch helper for Django session + CSRF JSON APIs. */
(function (root) {
  'use strict';

  var MODULES = {
    analyze: 1, images_type: 1, user_huaxiang: 1, zhiling: 1, ai_task: 1,
    weixin_baowen: 1, piliang_baowen: 1, ai_image: 1, b2b: 1, b2b_task: 1,
    user_contact: 1, b2b_order: 1, webmedia: 1, webmedia_task: 1, webmedia_order: 1,
    media_collection: 1, zimedia: 1, zimedia_order: 1, weixinapp2: 1, draft: 1,
    weixin_article: 1, user_site: 1, user_site_task: 1, user_site_record: 1,
    user_tdk: 1, user_jianji: 1, video_task: 1, video_record: 1, tongji: 1,
    shoulu_tuozhan: 1, shoulu_record: 1, agent_skill: 1, zhishu: 1, zhengliu: 1,
    tuozhan: 1, user_score_log: 1, user_money_log: 1, realname: 1, quanyi: 1
  };

  var PAGE_ALIASES = {
    'images_type-index-type-1': ['images_type', '1'],
    'images_type-index-type-2': ['images_type', '2'],
    'images_type-add': ['images_type', ''],
    'media_collection-index-type-1': ['media_collection', '1'],
    'media_collection-index-type-2': ['media_collection', '2'],
    'media_collection-add': ['media_collection', ''],
    'analyze_v2-add': ['analyze', 'v2'],
    'analyze-add': ['analyze', ''],
    'b2b-tougao-type-1': ['b2b', 'tougao-1'],
    'b2b-tougao-type-3': ['b2b', 'tougao-3'],
    'b2b-tougao-type-4': ['b2b', 'tougao-4'],
    'b2b-tougao-type-5': ['b2b', 'tougao-5'],
    'b2b-tougao-type-6': ['b2b', 'tougao-6'],
    'b2b-settle-type-2': ['b2b', 'settle-2'],
    'b2b-settle-type-8': ['b2b', 'settle-8'],
    'b2b-configure-type-2': ['b2b', 'configure-2'],
    'webmedia-tougao-media_id-21471': ['webmedia', 'tougao'],
    'zimedia-tougao-media_id-53781': ['zimedia', 'tougao']
  };

  var DEDICATED = {
    company_keyword: '/api/keywords/',
    'company_keyword-add': '/api/keywords/',
    company_question: '/api/questions/',
    'company_question-add': '/api/questions/',
    article: '/api/articles/',
    'article-add': '/api/articles/',
    article_type: '/api/article-types/',
    'article_type-add': '/api/article-types/'
  };

  function csrfToken() {
    var match = document.cookie.match(/(?:^|; )csrftoken=([^;]*)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function unwrapRow(data) {
    var out = {};
    Object.keys(data || {}).forEach(function (key) {
      var match = key.match(/^row\[([^\]]+)\]$/);
      out[match ? match[1] : key] = data[key];
    });
    return out;
  }

  function api(path, options) {
    options = options || {};
    var headers = Object.assign({
      'Accept': 'application/json',
      'X-Requested-With': 'XMLHttpRequest'
    }, options.headers || {});
    if (options.body != null && typeof options.body === 'object' && !(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(options.body);
    }
    var method = (options.method || 'GET').toUpperCase();
    if (method !== 'GET' && method !== 'HEAD') {
      headers['X-CSRFToken'] = csrfToken();
    }
    return fetch(path, Object.assign({}, options, {
      method: method,
      credentials: 'same-origin',
      headers: headers
    })).then(function (response) {
      var type = response.headers.get('content-type') || '';
      if (!/\bapplication\/json\b/i.test(type)) {
        return response.text().then(function () {
          return { ok: false, status: response.status, error: { code: 'http_error', message: '服务响应异常' } };
        });
      }
      return response.json().then(function (payload) {
        if (!payload || typeof payload !== 'object') {
          return { ok: false, status: response.status, error: { code: 'invalid_response', message: '响应格式错误' } };
        }
        if (!Object.prototype.hasOwnProperty.call(payload, 'ok')) {
          payload = { ok: response.ok, data: payload };
        }
        payload.status = response.status;
        return payload;
      });
    });
  }

  function resolveModule(pageKey) {
    if (!pageKey) return null;
    if (PAGE_ALIASES[pageKey]) {
      return { module: PAGE_ALIASES[pageKey][0], subtype: PAGE_ALIASES[pageKey][1] || '' };
    }
    var base = pageKey;
    if (base.slice(-4) === '-add') base = base.slice(0, -4);
    if (base.indexOf('-edit') !== -1) base = base.split('-edit')[0];
    if (base.indexOf('-index-type-') !== -1) {
      var parts = base.split('-index-type-');
      if (MODULES[parts[0]]) return { module: parts[0], subtype: parts[1] || '' };
    }
    if (base === 'company_keyword' || base === 'company_question' || base === 'article' || base === 'article_type' ||
        base === 'general-profile' || base === 'dashboard' || base === 'shell') {
      return null;
    }
    if (MODULES[base]) return { module: base, subtype: '' };
    return null;
  }

  function resourceFor(pageKey) {
    if (DEDICATED[pageKey]) return DEDICATED[pageKey];
    if (/^company_keyword-edit/.test(pageKey)) return '/api/keywords/';
    if (/^company_question-edit/.test(pageKey)) return '/api/questions/';
    if (/^article_type-edit/.test(pageKey)) return '/api/article-types/';
    if (/^article-edit/.test(pageKey)) return '/api/articles/';
    var resolved = resolveModule(pageKey);
    if (!resolved) return null;
    var url = '/api/modules/' + resolved.module + '/';
    if (resolved.subtype) url += '?subtype=' + encodeURIComponent(resolved.subtype);
    return url;
  }

  function resourceMeta(pageKey) {
    if (DEDICATED[pageKey] || /^company_keyword-edit/.test(pageKey) || /^company_question-edit/.test(pageKey) ||
        /^article_type-edit/.test(pageKey) || /^article-edit/.test(pageKey)) {
      return { dedicated: true, resource: resourceFor(pageKey), module: null, subtype: '' };
    }
    var resolved = resolveModule(pageKey);
    if (!resolved) return null;
    return {
      dedicated: false,
      module: resolved.module,
      subtype: resolved.subtype || '',
      resource: resourceFor(pageKey)
    };
  }

  function upload(files, options) {
    options = options || {};
    var form = new FormData();
    var list = files instanceof FileList ? Array.prototype.slice.call(files) : [].concat(files || []);
    list.forEach(function (file) {
      if (file) form.append('file', file);
    });
    if (options.category) form.append('category', options.category);
    return api('/api/upload', { method: 'POST', body: form });
  }

  function getRecord(resource, id) {
    if (!resource || id == null || id === '') return Promise.resolve({ ok: false, error: { message: '缺少资源' } });
    var base = String(resource).split('?')[0];
    var query = 'id=' + encodeURIComponent(id);
    var subtypeMatch = String(resource).match(/[?&]subtype=([^&]*)/);
    if (subtypeMatch) query += '&subtype=' + subtypeMatch[1];
    return api(base + (base.indexOf('?') === -1 ? '?' : '&') + query);
  }

  root.GeoAPI = Object.freeze({
    csrfToken: csrfToken,
    unwrapRow: unwrapRow,
    request: api,
    resourceFor: resourceFor,
    resourceMeta: resourceMeta,
    resolveModule: resolveModule,
    upload: upload,
    getRecord: getRecord,
    me: function () { return api('/api/auth/me'); },
    dashboard: function () { return api('/api/dashboard'); },
    wallet: function (body) { return api('/api/auth/wallet', { method: 'POST', body: body }); },
    login: function (body) { return api('/api/auth/login', { method: 'POST', body: body }); },
    logout: function () { return api('/api/auth/logout', { method: 'POST', body: {} }); },
    profile: function (body) { return api('/api/auth/profile', { method: 'PUT', body: body }); }
  });
}(typeof window === 'undefined' ? globalThis : window));
