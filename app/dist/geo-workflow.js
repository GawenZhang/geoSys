(function () {
  'use strict';

  const find = (selector) => document.querySelector(selector);
  const escape = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[character]);
  const knowledgeUrl = '/api/pipeline/knowledge/';
  const observationsUrl = '/api/pipeline/observations/';
  const phaseLabel = (value) => value === 'baseline' ? '基线' : '复测';
  const intentLabel = (value) => value === 'category' ? '品类问题' : '品牌问题';
  const cohortLabel = (value) => ({ target: '优化组', holdout: '观察组' })[value] || '未分组';

  async function request(path, options) {
    const result = await window.GeoAPI.request(path, options);
    if (!result.ok) throw new Error(result.error?.message || '请求失败，请重试。');
    return result.data;
  }

  function status(form, message = '', error = false) {
    const feedback = form.querySelector('[data-status]');
    feedback.textContent = message;
    feedback.toggleAttribute('data-error', error);
  }

  function onSubmit(form, handler) {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const button = form.querySelector('[type=submit]');
      if (button.disabled) return;
      button.disabled = true;
      try {
        await handler();
      } catch (error) {
        if (form.querySelector('[data-status]')) status(form, error.message, true);
      } finally {
        button.disabled = false;
      }
    });
  }

  function initKnowledge(form) {
    const fields = form.elements;
    const newRecord = find('#geo-knowledge-new');
    const list = find('#geo-knowledge-list');
    const extractKeywords = initKeywordExtraction();
    const updateFields = () => {
      newRecord.hidden = newRecord.disabled = Boolean(fields.record_id.value);
    };
    const selectRecord = (id) => {
      fields.record_id.value = String(id || '');
      updateFields();
    };

    async function load(selected) {
      try {
        const data = await request(knowledgeUrl);
        fields.record_id.replaceChildren(new Option('新建知识库', ''));
        for (const { id, name } of data.items) {
          fields.record_id.add(new Option(name, id));
        }
        selectRecord(selected);
        list.innerHTML = data.items.map(({ id, name, chunks }) => '<li><strong>' + escape(name) + '</strong> · '
          + chunks + ' 段<div class="geo-links geo-knowledge-actions">'
          + '<button class="geo-button geo-button-secondary" type="button" data-knowledge="' + id + '">追加资料</button>'
          + '<button class="geo-button geo-button-secondary" type="button" data-extract="' + id + '" data-name="'
          + escape(name) + '">提取关键词</button></div></li>').join('') || '<li>还没有知识库。可直接在表单中创建。</li>';
      } catch (error) {
        list.textContent = '知识库列表加载失败。' + error.message;
      }
    }

    fields.record_id.addEventListener('change', updateFields);
    list.addEventListener('click', (event) => {
      const extract = event.target.closest('[data-extract]');
      if (extract) {
        extractKeywords(extract.dataset.extract, extract.dataset.name);
        return;
      }
      const button = event.target.closest('[data-knowledge]');
      if (!button) return;
      selectRecord(button.dataset.knowledge);
      fields.text.focus();
    });
    onSubmit(form, async () => {
      status(form, '正在保存和提取资料…');
      const data = new FormData(form);
      if (!fields.file.files.length) data.delete('file');
      const result = await request(knowledgeUrl, { method: 'POST', body: data });
      form.reset();
      status(form, '已保存到「' + result.name + '」，当前可检索 ' + result.chunks + ' 段。');
      await load(result.id);
    });
    load();
  }

  function initKeywordExtraction() {
    const panel = find('#geo-keyword-panel');
    const heading = find('#geo-keyword-heading');
    const form = find('#geo-keyword-form');
    const candidates = find('#geo-keyword-candidates');
    const actions = find('#geo-keyword-actions');
    const submit = form.querySelector('[type=submit]');
    let selectedUrl = '';
    let revision = 0;

    onSubmit(form, async () => {
      const selected = Array.from(candidates.querySelectorAll('.geo-keyword-list-item'))
        .filter((row) => row.querySelector('[type=checkbox]').checked);
      if (!selected.length) throw new Error('请先勾选要保存的业务关键词。');
      const keywords = selected.map((row) => row.querySelector('[type=text]').value.trim());
      status(form, '正在保存业务关键词…');
      const saved = await request(selectedUrl, { method: 'PUT', body: { keywords } });
      selected.forEach((row) => {
        const checkbox = row.querySelector('[type=checkbox]');
        checkbox.checked = false;
        checkbox.disabled = true;
        row.querySelector('[type=text]').disabled = true;
        row.querySelector('[data-keyword-state]').textContent = '已在业务关键词列表';
      });
      status(form, '已保存 ' + saved.created + ' 个业务关键词，已有同名词 ' + saved.skipped + ' 个。');
    });

    return async (id, name) => {
      if (submit.disabled) return;
      const version = ++revision;
      selectedUrl = knowledgeUrl + id + '/' + 'keywords';
      heading.textContent = '从「' + name + '」提取业务关键词';
      panel.hidden = false;
      actions.hidden = true;
      candidates.replaceChildren();
      status(form, '正在提取候选词…');
      heading.focus();
      try {
        const data = await request(selectedUrl, { method: 'POST', body: {} });
        if (version !== revision) return;
        if (!data.items.length) {
          status(form, '没找到明确的业务词。先追加具体产品或服务，例如「主营业务：工业水泵、变频控制柜」，再提取一次。');
          return;
        }
        candidates.innerHTML = data.items.map((item, index) => {
          const disabled = item.existing ? ' disabled' : '';
          const id = 'geo-candidate-' + index;
          return '<div class="geo-keyword-list-item"><div><label for="' + id + '">'
            + '<input type="checkbox" id="' + id + '" aria-label="选中候选词 ' + escape(item.keyword)
            + '"' + disabled + '> 保存这个词</label>'
            + '<input type="text" class="geo-keyword-input" maxlength="32" aria-label="编辑业务关键词 '
            + escape(item.keyword) + '" value="' + escape(item.keyword) + '"' + disabled + '></div>'
            + '<p class="geo-help">资料原文 · ' + escape(item.evidence)
            + '<br><span data-keyword-state>' + (item.existing ? '已在业务关键词列表' : '')
            + '</span></p></div>';
        }).join('');
        actions.hidden = false;
        status(form, '提取到 ' + data.items.length + ' 个候选词。');
      } catch (error) {
        if (version === revision) status(form, error.message, true);
      }
    };
  }

  function fraction(count, total) {
    return total ? count + '/' + total + '（' + Math.round(100 * count / total) + '%）' : '—';
  }

  function renderSummary(element, rows) {
    if (!rows.length) {
      element.textContent = '暂无采样。保存第一条真实回答后，这里会显示基线或复测数据。';
      return;
    }
    element.innerHTML = '<table><thead><tr><th>品牌</th><th>平台 / 入口</th><th>阶段</th><th>问题类型</th>'
      + '<th>品牌提及</th><th>明确推荐</th><th>自有引用</th><th>采集失败</th></tr></thead><tbody>'
      + rows.map((item) => '<tr><td>' + escape(item.brand) + '</td><td>'
        + escape(item.platform) + ' / ' + escape(item.surface) + '</td><td>' + phaseLabel(item.phase)
        + '</td><td>' + intentLabel(item.intent) + '</td><td>' + fraction(item.mentioned, item.valid)
        + '</td><td>' + fraction(item.recommended, item.valid) + '</td><td>'
        + fraction(item.own_cited, item.citation_samples) + '</td><td>' + item.failed + '</td></tr>').join('')
      + '</tbody></table>';
  }

  function renderComparison(element, rows) {
    if (!rows.length) {
      element.textContent = '录入有效回答后，可在这里看逐题对照。';
      return;
    }
    const metrics = (sample) => sample.valid
      ? sample.valid + ' 条 · ' + sample.dates + ' 天<br>提及 ' + fraction(sample.mentioned, sample.valid)
        + '<br>推荐 ' + fraction(sample.recommended, sample.valid)
        + '<br>官网引用 ' + fraction(sample.own_cited, sample.citation_samples)
      : '待采样';
    element.innerHTML = '<table class="geo-comparison"><thead><tr><th>问题 / 入口</th><th>基线</th><th>复测</th>'
      + '<th>信源与变化</th></tr></thead><tbody>'
      + rows.map((row) => {
        const sources = row.sources.length ? '<details><summary>品牌缺席时的基线信源</summary><ul>'
          + row.sources.map(({ url, answers }) => '<li><a href="' + escape(url)
            + '" target="_blank" rel="noopener noreferrer">' + escape(url) + '</a> · ' + answers + ' 条回答</li>').join('')
          + '</ul></details>' : '';
        const signals = row.signals.map((signal) => signal === 'recommendation' ? '跨日新增推荐' : '跨日新增官网引用');
        return '<tr><th scope="row">' + escape(row.question) + '<br><span class="geo-help">'
          + escape([row.trial, row.brand, row.platform, row.surface].filter(Boolean).join(' · ')) + '<br>'
          + intentLabel(row.intent) + ' · ' + cohortLabel(row.cohort) + '</span></th><td>' + metrics(row.baseline)
          + '</td><td>' + metrics(row.retest) + '</td><td>'
          + (signals.length ? '<strong>' + signals.join(' · ') + '</strong>' : '')
          + (sources || (signals.length ? '' : '—')) + '</td></tr>';
      }).join('') + '</tbody></table>';
  }

  function renderObservations(element, items) {
    element.innerHTML = items.map((item) => {
      const sources = item.citations.map((url) => '<li><a href="' + escape(url) + '" target="_blank" rel="noopener noreferrer">'
        + escape(url) + '</a></li>').join('');
      const retest = item.phase === 'baseline' ? '<button type="button" class="geo-button" data-retest="' + item.id + '">沿用原题复测</button>' : '';
      const citationLabel = { yes: '已取得链接', no: '确认无引用', unknown: '无法判定' }[item.citation_status];
      const verdict = item.outcome === 'answer' ? '<p>' + (item.mentioned ? '提到品牌' : '未提到品牌')
        + ' · ' + (item.recommended ? '明确推荐' : '未明确推荐') + ' · ' + citationLabel + '</p>' : '';
      return '<details class="geo-observation-record"><summary>' + escape(item.question) + ' · ' + escape(item.platform)
        + ' · ' + phaseLabel(item.phase) + ' · ' + (item.outcome === 'failed' ? '采集失败' : '有效回答') + '</summary>'
        + '<p class="geo-help">' + escape([item.trial, item.brand, item.surface].filter(Boolean).join(' · '))
        + ' · ' + intentLabel(item.intent) + ' · ' + cohortLabel(item.cohort)
        + ' · ' + escape(new Date(item.observed_at).toLocaleString('zh-CN')) + '</p>'
        + '<p class="geo-answer">' + escape(item.answer) + '</p>' + verdict
        + (sources ? '<ul class="geo-record-list">' + sources + '</ul>' : '')
        + '<div class="geo-links">' + retest + '<button type="button" class="geo-button geo-button-secondary" data-edit="'
        + item.id + '">编辑记录</button></div></details>';
    }).join('');
  }

  function initObservations(form) {
    const fields = form.elements;
    const filter = find('#geo-observation-filter');
    const summaries = find('#geo-observation-summary');
    const comparison = find('#geo-question-comparison');
    const list = find('#geo-observation-list');
    const pages = find('#geo-observation-pages');
    const judgments = find('#geo-observation-judgments');
    const citations = find('#geo-citation-links');
    const cancel = find('#geo-observation-cancel');
    const submit = form.querySelector('[type=submit]');
    let items = [];
    let requested = 0;

    function updateFields() {
      judgments.hidden = judgments.disabled = fields.outcome.value === 'failed';
      citations.hidden = fields.citation_status.value !== 'yes';
      fields.citations.disabled = citations.hidden;
      fields.citations.required = !citations.hidden;
      fields.owned_site.required = !judgments.disabled && fields.citation_status.value !== 'unknown';
      fields.trial.required = Boolean(fields.cohort.value);
    }

    function clearSample() {
      for (const key of ['id', 'observed_at', 'question', 'answer', 'citations']) fields[key].value = '';
      fields.outcome.value = 'answer';
      fields.citation_status.value = 'unknown';
      fields.mentioned.checked = fields.recommended.checked = false;
      find('#geo-observation-title').textContent = '记录一次采样';
      submit.textContent = '保存采样';
      cancel.hidden = true;
      updateFields();
    }

    async function load(page = 1) {
      const version = ++requested;
      try {
        const query = new URLSearchParams(new FormData(filter));
        query.set('page', page);
        const data = await request(observationsUrl + '?' + query);
        if (version !== requested) return;
        items = data.items;
        renderSummary(summaries, data.summary);
        renderComparison(comparison, data.questions || []);
        renderObservations(list, items);
        const lastPage = Math.max(1, Math.ceil(data.total / data.page_size));
        const link = (label, target) => '<button type="button" class="geo-button geo-button-secondary" data-page="'
          + target + '">' + label + '</button>';
        pages.innerHTML = (page > 1 ? link('上一页', page - 1) : '') + '<span>第 ' + page + ' / '
          + lastPage + ' 页 · ' + data.total + ' 条</span>' + (page < lastPage ? link('下一页', page + 1) : '');
      } catch (error) {
        if (version !== requested) return;
        summaries.textContent = '采样结果加载失败。' + error.message;
        comparison.replaceChildren();
        list.replaceChildren();
        pages.replaceChildren();
      }
    }

    fields.outcome.addEventListener('change', updateFields);
    fields.citation_status.addEventListener('change', updateFields);
    fields.cohort.addEventListener('change', updateFields);
    cancel.addEventListener('click', () => { clearSample(); status(form); });
    onSubmit(filter, () => load());
    pages.addEventListener('click', (event) => {
      const button = event.target.closest('[data-page]');
      if (button) load(Number(button.dataset.page));
    });
    list.addEventListener('click', (event) => {
      const button = event.target.closest('[data-edit],[data-retest]');
      if (!button) return;
      const item = items.find((row) => row.id === Number(button.dataset.edit || button.dataset.retest));
      if (!item) return;
      clearSample();
      status(form);
      for (const key of ['trial', 'cohort', 'brand', 'owned_site', 'platform', 'surface', 'question', 'intent']) {
        fields[key].value = item[key] || '';
      }
      fields.phase.value = button.dataset.retest ? 'retest' : item.phase;
      if (button.dataset.edit) {
        for (const key of ['id', 'outcome', 'answer', 'citation_status']) fields[key].value = item[key];
        const date = new Date(item.observed_at);
        date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
        fields.observed_at.value = date.toISOString().slice(0, 16);
        fields.citations.value = item.citations.join('\n');
        fields.mentioned.checked = item.mentioned;
        fields.recommended.checked = item.recommended;
        find('#geo-observation-title').textContent = '编辑采样';
        submit.textContent = '保存修改';
        cancel.hidden = false;
      }
      updateFields();
      fields.answer.focus();
    });
    onSubmit(form, async () => {
      const data = Object.fromEntries(new FormData(form));
      if (data.observed_at) data.observed_at = new Date(data.observed_at).toISOString();
      const method = data.id ? 'PUT' : 'POST';
      if (data.outcome === 'failed') data.citation_status = 'unknown';
      status(form, '正在保存…');
      const result = await request(observationsUrl, { method, body: data });
      clearSample();
      status(form, method === 'PUT' ? '已保存修改。' : '已保存「' + phaseLabel(result.phase) + '」采样。');
      filter.elements.brand.value = result.brand;
      filter.elements.trial.value = result.trial || '';
      await load();
    });
    updateFields();
    load();
  }

  window.GeoWorkflow = {
    init() {
      const knowledge = find('#geo-knowledge-form');
      const observations = find('#geo-observation-form');
      if (knowledge) initKnowledge(knowledge);
      if (observations) initObservations(observations);
    }
  };
}());
