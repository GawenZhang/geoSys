/* Local interaction layer for the captured FastAdmin / Layui interface. */
(function () {
  'use strict';
  var body = document.body;
  var pageKey = body.dataset.pageKey || location.pathname.split('/').pop().replace('.html', '');
  var shell = pageKey === 'shell' || !!document.querySelector('.main-sidebar');
  var routes = {};
  var stateKey = 'geo-local-page:' + pageKey;
  var table = document.querySelector('.fixed-table-body table') || document.querySelector('#table');
  var activeModal = null;
  var originalRows = table && table.tBodies[0] ? table.tBodies[0].innerHTML : '';
  var page = 1, pageSize = 10, filtered = null;
  var editors=[];
  var modalLayouts={};
  var manualKeywordMarkup="<div class=\"keyword_block keyword_all\">\n        <div class=\"keyword_item\">\n            <p>前缀（换行，一行一个，0-20个） </p>\n            <textarea  class=\"form-control \" id=\"prefixes\" name=\"row[pre_keywords]\" data-rule=\"\" rows=\"20\" type=\"text\" placeholder=\"前缀如：\n推荐\n求推荐\n推荐一下\n靠谱的\n口碑好的\n口碑不错的\n诚信的\n专业的\n实力强的\n售后完善的\"></textarea>\n        </div>\n        <div class=\"keyword_item\">\n            <p>主词（必须包含关键词，1-20个）</p>\n            <textarea   class=\"form-control\" id=\"main-words\" name=\"row[tuozhan_keywords]\" data-rule=\"\" rows=\"20\" type=\"text\" placeholder=\"主词相关，比如主词是：GEO\n这里可以写：\n\nGEO优化\nGEO优化软件\nGEO软件\n\"></textarea>\n        </div>\n        <div class=\"keyword_item\">\n            <p>后缀（换行，一行一个，0-20个） </p>\n            <textarea  id=\"suffixes\" class=\"form-control\" name=\"row[next_keywords]\" data-rule=\"\" rows=\"20\" type=\"text\" placeholder=\"后缀如：\n厂家\n生产厂家\n源头厂家\n供应商\n公司\n服务商\n渠道\n机构\n方案\n平台\n权威平台\n管理平台\"></textarea>\n        </div>\n    </div>";
  if(new URLSearchParams(location.search).has('localDialog')&&new URLSearchParams(location.search).get('originalDialog')!=='0')body.classList.add('is-dialog');
  // The shipped Bootstrap widget implementations own dropdown/tab behavior;
  // this local router supplies their delegated event boundary for static pages.
  if(window.jQuery){window.jQuery(document).off('.bs.dropdown.data-api').off('.bs.tab.data-api');}
  function one(selector, root) { return (root || document).querySelector(selector); }
  function all(selector, root) { return Array.from((root || document).querySelectorAll(selector)); }
  function escapeHTML(text) { return String(text == null ? '' : text).replace(/[&<>"']/g, function(c) {return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];}); }
  function layer() { return window.layer || (window.layui && window.layui.layer); }
  function message(text) {
    if (layer()) return layer().msg(text, {time: 2600});
    var toast = document.createElement('div'); toast.className = 'geo-toast'; toast.setAttribute('role','status'); toast.textContent = text;
    body.appendChild(toast); setTimeout(function(){toast.remove();}, 2600);
  }
  function normalize(url) {
    try { return new URL(url, location.origin).pathname.replace(/\/$/,''); } catch(e) { return ''; }
  }
  function routeFor(url) {
    var path = normalize(url), result = routes[path];
    if (result && typeof result === 'object') return result.file || result.local || result.output;
    if (result) return result;
    // Every edit record uses the same sampled form, with local row values supplied separately.
    var match = path.match(/^(.*\/(?:media_id|id|ids)\/)\d+$/);
    if (match) { var key = Object.keys(routes).find(function(k){return k.startsWith(match[1]);}); if(key) return routeFor(key); }
    return null;
  }
  function titleFor(path) {
    var anchor = all('.sidebar-menu a[href]').find(function(a){return normalize(a.getAttribute('href')) === normalize(path);});
    return anchor ? anchor.textContent.trim() : document.title;
  }
  function layoutSelector(layouts,control){
    if(!layouts)return null;
    var direct=Object.keys(layouts).find(function(selector){try{return control.matches(selector);}catch(e){return false;}});if(direct)return direct;
    function family(url){return normalize(url).replace(/\/(media_id|id|ids)\/\d+/g,'/$1/{record}');}
    var path=family(actionURL(control));return Object.keys(layouts).find(function(selector){return layouts[selector].url&&family(layouts[selector].url)===path;});
  }
  function apiResource() {
    return window.GeoAPI ? window.GeoAPI.resourceFor(pageKey) : null;
  }
  function apiResourceBase() {
    var resource = apiResource();
    return resource ? resource.split('?')[0] : null;
  }
  var listQuery = {};
  function apiListUrl() {
    var resource = apiResource();
    if (!resource) return null;
    var params = Object.assign({ page: 1, page_size: 100 }, listQuery || {});
    var query = Object.keys(params).filter(function (key) {
      return params[key] != null && String(params[key]).trim() !== '';
    }).map(function (key) {
      return encodeURIComponent(key) + '=' + encodeURIComponent(params[key]);
    }).join('&');
    return resource + (resource.indexOf('?') === -1 ? '?' : '&') + query;
  }
  function editRecordId() {
    var params = new URLSearchParams(location.search);
    if (params.get('editId')) return params.get('editId');
    var pathMatch = location.pathname.match(/\/(?:ids|id)\/(\d+)/);
    if (pathMatch) return pathMatch[1];
    var keyMatch = pageKey.match(/-edit-ids?-(\d+)/);
    if (keyMatch) return keyMatch[1];
    var form = one('form');
    return (form && form.dataset.id) || body.dataset.id || '';
  }
  function apiSubtype() {
    var meta = window.GeoAPI && window.GeoAPI.resourceMeta(pageKey);
    return (meta && meta.subtype) || '';
  }
  function ensureAuth() {
    if (!window.GeoAPI || new URLSearchParams(location.search).has('localDialog')) return Promise.resolve(true);
    return window.GeoAPI.me().then(function (result) {
      if (result.ok) return true;
      location.href = '/user/index/login/';
      return false;
    }).catch(function () {
      location.href = '/user/index/login/';
      return false;
    });
  }
  function buildApiBody(values) {
    var raw = window.GeoAPI ? window.GeoAPI.unwrapRow(values) : values;
    var body = Object.assign({}, raw);
    if (body.type_name && !body.name) body.name = body.type_name;
    if (body.company_keyword_id) body.company_keyword_id = Number(body.company_keyword_id) || body.company_keyword_id;
    if (body.type_id) body.type_id = Number(body.type_id) || body.type_id;
    if (body.image_type_id) body.image_type_id = Number(body.image_type_id) || body.image_type_id;
    if (body.tuozhan_status != null) body.tuozhan_status = Number(body.tuozhan_status);
    if (body.status != null && body.status !== '') body.status = Number(body.status);
    if (body.content == null) {
      var editor = one('textarea[name="row[content]"],#c-content,.edui-default textarea');
      if (editor) body.content = editor.value;
    }
    var subtype = apiSubtype();
    if (subtype) body.subtype = subtype;
    return body;
  }
  function nestedValue(item, field) {
    if (!field) return '';
    if (Object.prototype.hasOwnProperty.call(item, field) && item[field] != null) return item[field];
    if (item.data && Object.prototype.hasOwnProperty.call(item.data, field) && item.data[field] != null) return item.data[field];
    if (field.indexOf('.') !== -1) {
      var parts = field.split('.');
      var cursor = item;
      for (var i = 0; i < parts.length; i++) {
        if (cursor == null) return '';
        cursor = cursor[parts[i]] != null ? cursor[parts[i]] : (cursor.data && cursor.data[parts[i]]);
      }
      return cursor == null ? '' : cursor;
    }
    if (field === 'addtime') return (item.addtime || item.created_at || '').toString().replace('T', ' ').slice(0, 19);
    if (field === 'created_at') return (item.created_at || '').toString().replace('T', ' ').slice(0, 19);
    return '';
  }
  function operateCell(item) {
    var basePath = (body.dataset.pagePath || ('/user/' + pageKey.split('-')[0])).replace(/\/$/, '');
    var extra = '';
    if (pageKey === 'link_pool') extra += '<a href="javascript:;" class="btn btn-xs btn-info geo-check-link" data-id="'+item.id+'">检查</a> ';
    if (pageKey === 'publish_order' && item.status !== 'confirmed' && item.status !== 'rejected') {
      var next = {pending:['claimed','领取'], claimed:['submitted','提交回执'], submitted:['confirmed','确认完成']}[item.status];
      if (next) extra += '<a href="javascript:;" class="btn btn-xs btn-primary geo-order-action" data-id="'+item.id+'" data-status="'+next[0]+'">'+next[1]+'</a> ';
      extra += '<a href="javascript:;" class="btn btn-xs btn-warning geo-order-action" data-id="'+item.id+'" data-status="rejected">退回</a> ';
    }
    return '<td>'+extra+'<a href="javascript:;" class="btn btn-xs btn-success btn-editone" data-url="'+escapeHTML(basePath)+'/add" data-id="'+item.id+'">编辑</a> <a href="javascript:;" class="btn btn-xs btn-danger btn-delone" data-id="'+item.id+'">删除</a></td>';
  }
  function rowCellsFor(item) {
    var statusLabel = ({0:'待审核',1:'正常',2:'禁用'})[item.status] || String(item.status == null ? '' : item.status);
    if (pageKey === 'company_keyword') {
      return [
        '<td class="bs-checkbox"><input name="btSelectItem" type="checkbox" data-id="'+item.id+'"></td>',
        '<td>'+item.id+'</td>',
        '<td>'+escapeHTML(item.keyword)+'</td>',
        '<td>'+escapeHTML(String((item.zhengliu_question||'').split(/\r?\n/).filter(Boolean).length))+'</td>',
        '<td>'+(item.tuozhan_status ? '自动拓词' : '不拓词')+'</td>',
        '<td>'+escapeHTML((item.created_at||'').replace('T',' ').slice(0,19))+'</td>',
        operateCell(item)
      ].join('');
    }
    if (pageKey === 'company_question') {
      return [
        '<td class="bs-checkbox"><input name="btSelectItem" type="checkbox" data-id="'+item.id+'"></td>',
        '<td>'+item.id+'</td>',
        '<td>'+escapeHTML(item.company_keyword||'')+'</td>',
        '<td style="text-align:left">'+escapeHTML((item.question||'').split(/\r?\n/)[0]||'')+'</td>',
        '<td>'+escapeHTML((item.created_at||'').replace('T',' ').slice(0,19))+'</td>',
        operateCell(item)
      ].join('');
    }
    if (pageKey === 'article_type') {
      return [
        '<td class="bs-checkbox"><input name="btSelectItem" type="checkbox" data-id="'+item.id+'"></td>',
        '<td>'+item.id+'</td>',
        '<td>'+escapeHTML(item.type_name)+'</td>',
        '<td>'+escapeHTML((item.created_at||'').replace('T',' ').slice(0,19))+'</td>',
        '<td><a href="javascript:;" class="btn btn-xs btn-danger btn-delone" data-id="'+item.id+'">删除</a></td>'
      ].join('');
    }
    if (pageKey === 'article') {
      var publicArticlePath = '/p/';
      return [
        '<td class="bs-checkbox"><input name="btSelectItem" type="checkbox" data-id="'+item.id+'"></td>',
        '<td>'+item.id+'</td>',
        '<td>'+escapeHTML(item.type_name||'')+'</td>',
        '<td>'+escapeHTML(item.title)+'</td>',
        '<td>0</td>',
        '<td>0</td>',
        '<td>'+escapeHTML(statusLabel)+'</td>',
        '<td>'+escapeHTML((item.created_at||'').replace('T',' ').slice(0,19))+'</td>',
        '<td><a href="javascript:;" class="btn btn-xs btn-success btn-editone" data-url="/user/article/add" data-id="'+item.id+'">编辑</a> <a href="javascript:;" class="btn btn-xs btn-info geo-optimize" data-id="'+item.id+'">优化</a> <a class="btn btn-xs btn-default" href="'+publicArticlePath+item.id+'" target="_blank" rel="noopener">阅读</a> <a href="javascript:;" class="btn btn-xs btn-danger btn-delone" data-id="'+item.id+'">删除</a></td>'
      ].join('');
    }
    if (!table || !table.tHead || !table.tHead.rows[0]) {
      return '<td class="bs-checkbox"><input name="btSelectItem" type="checkbox" data-id="'+item.id+'"></td><td>'+item.id+'</td><td>'+escapeHTML(item.title||item.name||'')+'</td>'+operateCell(item);
    }
    return Array.from(table.tHead.rows[0].cells).map(function (th) {
      var field = th.dataset.field;
      if (th.classList.contains('bs-checkbox') || field === '0') {
        return '<td class="bs-checkbox"><input name="btSelectItem" type="checkbox" data-id="'+item.id+'"></td>';
      }
      if (field === 'operate' || /操作/.test(th.textContent || '')) return operateCell(item);
      if (!field) return '<td>'+item.id+'</td>';
      if (field === 'status') return '<td>'+escapeHTML(statusLabel || nestedValue(item, field))+'</td>';
      var value = nestedValue(item, field);
      if (typeof value === 'string' && value.indexOf('\n') !== -1) value = value.split(/\r?\n/)[0];
      return '<td>'+escapeHTML(value == null ? '' : String(value))+'</td>';
    }).join('');
  }
  function loadRemoteRows() {
    var listUrl = apiListUrl();
    if (!listUrl || !table || !window.GeoAPI || /-add$|-edit|tougao|settle|configure/.test(pageKey)) return Promise.resolve();
    return window.GeoAPI.request(listUrl).then(function (result) {
      if (!result.ok) {
        message((result.error && result.error.message) || '加载数据失败');
        return;
      }
      var items = (result.data && result.data.items) || [];
      var tbody = table.tBodies[0];
      if (!tbody) return;
      var colCount = table.tHead?.rows[0]?.cells.length || 6;
      if (!items.length) {
        tbody.innerHTML = '<tr class="no-records-found"><td colspan="'+colCount+'">没有找到匹配的记录</td></tr>';
      } else {
        tbody.innerHTML = items.map(function (item) {
          return '<tr data-id="'+item.id+'">'+rowCellsFor(item)+'</tr>';
        }).join('');
      }
      originalRows = tbody.innerHTML;
      filtered = null;
      page = 1;
      refreshRows();
    }).catch(function () { message('无法连接后端接口'); });
  }
  function saveRemoteRecord(form, button) {
    var base = apiResourceBase();
    if (!base || !window.GeoAPI) return Promise.resolve(null);
    var body = buildApiBody(formData(form));
    var editId = (form && form.dataset.id) || (button && button.dataset && button.dataset.id) || editRecordId() || '';
    var pathMatch = location.pathname.match(/\/(?:ids|id)\/(\d+)/);
    if (!editId && pathMatch) editId = pathMatch[1];
    if (!editId && /-edit-ids-(\d+)/.test(pageKey)) editId = pageKey.match(/-edit-ids-(\d+)/)[1];
    var method = editId ? 'PUT' : 'POST';
    if (editId) body.id = Number(editId);
    return window.GeoAPI.request(base, { method: method, body: body }).then(function (result) {
      if (!result.ok) {
        message((result.error && result.error.message) || '保存失败');
        return null;
      }
      return result.data;
    });
  }
  function navigate(url) {
    var path = normalize(url);
    if (path === '/user/index/logout') {
      if (window.GeoAPI) {
        window.GeoAPI.logout().finally(function () {
          sessionStorage.removeItem('geo-demo-session');
          localStorage.removeItem('geo-demo-remember');
          location.href = '/user/index/login/';
        });
        return;
      }
      sessionStorage.removeItem('geo-demo-session');localStorage.removeItem('geo-demo-remember'); location.href='/user/index/login/';return;
    }
    if(path === '/user' || path === '/user/index/index')path='/user/geo-workflow';
    if (!routeFor(path)) { message('此入口没有可用的本地采样页面'); return; }
    if (!shell && parent !== window && typeof parent.GeoNavigate === 'function') { parent.GeoNavigate(path);return; }
    if (!shell) { location.href='/user/index/index/#'+encodeURIComponent(path); return; }
    var iframe = one('.content-wrapper iframe');
    if (iframe) { iframe.src=routeFor(path);iframe.title=titleFor(path); }
    all('.sidebar-menu li').forEach(function(li){li.classList.remove('active');});
    var menuLinks=all('.sidebar-menu a[href]').filter(function(a){return normalize(a.href)===path;});
    menuLinks.slice(0,1).forEach(function(a){
      a.parentElement.classList.add('active');
      var tools=a.closest('.geo-tools');if(tools)tools.open=true;
      var ul=a.closest('.treeview-menu');if(ul){ul.style.display='block';ul.parentElement.classList.add('active');}
    });
    if(location.hash !== '#'+encodeURIComponent(path))history.replaceState(null,'','#'+encodeURIComponent(path));
    body.classList.remove('sidebar-open');
  }
  window.GeoNavigate = navigate;
  function modal(url, control) {
    var file=routeFor(url);
    if(!file) { message('该弹窗尚无可用的本地采样内容'); return; }
    var area=['80%','90%'];try{area=JSON.parse(control.dataset.area||'null')||area;}catch(e){}
    var widthKey=innerWidth<600?'390':'1440',layouts=modalLayouts[pageKey]&&modalLayouts[pageKey][widthKey];
    var match=layoutSelector(layouts,control);
    var layout=match&&layouts[match];if(layout){area=[layout.width,layout.height];if(layout.url&&routeFor(layout.url)){url=layout.url;file=routeFor(url);}}
    var title=control.dataset.title||control.title||control.textContent.trim()||'详情';
    activeModal={url:url,control:control,row:control.closest('tr'),index:null};
    var fastDialog=layout?/[?&]dialog=1(?:&|$)/.test(layout.url||''):true;
    var editId=control.dataset.id||(url.match(/\/(?:ids|id)\/(\d+)/)||[])[1]||'';
    var frameUrl=file+'?localDialog=1&originalDialog='+(fastDialog?'1':'0')+(editId?'&editId='+encodeURIComponent(editId):'');
    var skin=layout&&Object.prototype.hasOwnProperty.call(layout,'skin')?layout.skin:'layui-layer-fast';
    if(skin.includes('layui-layer-fast'))skin+=' layui-layer-border';
    if(layer())activeModal.index=layer().open({type:2,title:title,area:area,offset:layout?[layout.top,layout.left]:'auto',skin:skin,shade:layout?.shade??0,shadeClose:true,maxmin:layout?.maxmin??true,content:frameUrl,success:function(layero,index){
      var panel=layero[0]||layero,frame=one('iframe',panel);
      function attachFooter(){try{
        if(!fastDialog)return;
        var child=frame.contentDocument;if(!child)return;var sourceFooter=one('.layer-footer',child);if(!sourceFooter||one('.layui-layer-footer',panel))return;
        var footer=document.createElement('div');footer.className='layui-layer-btn layui-layer-footer';footer.innerHTML='<div class="row">'+sourceFooter.innerHTML+'</div>';panel.appendChild(footer);
        var originalButtons=all('button,a',sourceFooter);all('button,a',footer).forEach(function(button,i){button.addEventListener('click',function(event){event.preventDefault();event.stopPropagation();originalButtons[i]?.click();});});
        frame.style.height=Math.max(0,panel.clientHeight-(one('.layui-layer-title',panel)?.offsetHeight||0)-footer.offsetHeight)+'px';
      }catch(e){}}
      frame.addEventListener('load',attachFooter);setTimeout(attachFooter,100);setTimeout(attachFooter,700);
    }});
    else {
      var dialog=document.createElement('dialog');dialog.className='geo-dialog';
      dialog.innerHTML='<header>'+escapeHTML(title)+'<button type="button" aria-label="关闭">×</button></header><iframe title="'+escapeHTML(title)+'" src="'+frameUrl+'"></iframe>';
      dialog.querySelector('button').onclick=function(){dialog.close();dialog.remove();};body.appendChild(dialog);dialog.showModal();activeModal.dialog=dialog;
    }
  }
  function closeModal() {if(!activeModal)return;if(activeModal.dialog){activeModal.dialog.close();activeModal.dialog.remove();}else if(layer())layer().close(activeModal.index);activeModal=null;}
  function manualKeywords(){
    if(!layer())return;layer().open({title:'手动批量组合',content:manualKeywordMarkup,area:['90%','100%'],shadeClose:true,shade:0.8,btn:['确定'],yes:function(index){
      var keyword=(one('#c-keyword')?.value||'').trim();if(!keyword)return message('请输入主关键词');
      function lines(selector){return (one(selector)?.value||'').split(/\r?\n/).map(function(value){return value.trim();}).filter(Boolean);}
      var prefixes=lines('#prefixes'),mainWords=lines('#main-words'),suffixes=lines('#suffixes');
      if(!mainWords.length)return message('请至少输入1个拓展主词');
      if(Math.max(prefixes.length,mainWords.length,suffixes.length)>20)return message('每组最多输入20条');
      if(mainWords.some(function(word){return !word.includes(keyword);}))return message('主词必须包含关键词');
      var results=[];(prefixes.length?prefixes:['']).forEach(function(prefix){mainWords.forEach(function(word){(suffixes.length?suffixes:['']).forEach(function(suffix){results.push(prefix+word+suffix);});});});
      var output=one('.zhengliu_question_input');output.value=Array.from(new Set(results)).join('\n');output.textContent=output.value;layer().close(index);message('已生成 '+results.length+' 条本地组合');
    }});
  }
  function formData(form) {
    editors.forEach(function(item){if(item.editor.isReady)item.input.value=item.editor.getContent();});
    all('.edui-editor iframe').forEach(function(frame){try{var textarea=one('textarea',frame.closest('.form-group')||form||document);if(textarea&&frame.contentDocument)textarea.value=frame.contentDocument.body.innerHTML;}catch(e){}});
    var data={};all('input,textarea,select',form||document).forEach(function(input,i){
      if(input.disabled || input.type==='password' || input.type==='file' || ((input.type==='checkbox'||input.type==='radio')&&!input.checked))return;
      if(input.tagName==='SELECT'&&input.multiple){
        var picked=Array.from(input.selectedOptions).map(function(option){return option.value;}).filter(function(value){return value&&value!=='0';});
        data[input.name||input.id||('field_'+i)]=picked;
        return;
      }
      // Keep meaningful hidden fields (upload URLs, avatar) but skip CSRF/layout noise.
      if(input.type==='hidden'){
        var hiddenName=input.name||input.id||'';
        if(!/^row\[/.test(hiddenName) && !/^c-/.test(hiddenName) && hiddenName!=='id')return;
      }
      var key=input.name||input.id||input.className.split(' ')[0]||'field_'+i;
      data[key]=input.value;
    });
    if(pageKey==='user_tdk-add'&&form?.id==='entryForm'){data={};['type_name','phone','zhuti'].forEach(function(key){data[key]=(one('#'+key,form)?.value||'').trim();});tdkGroups.forEach(function(group){data[group]=tdkValues(group).join(group==='descs'?'@@':',');});}
    return data;
  }
  function validation(form) {
    var invalid=all('input,textarea,select',form||document).find(function(input){
      return !input.disabled && input.type!=='hidden' && input.offsetParent !== null && (input.required || /required/.test(input.dataset.rule||'')) && !input.value.trim();
    });
    if(invalid){invalid.focus();message('请填写'+(invalid.placeholder||'必填项'));return false;}
    if(pageKey==='user_tdk-add'&&form?.id==='entryForm'){var requiredGroup=['keywords','citys','companys'].find(function(group){return !tdkValues(group).length;});if(requiredGroup){one('#'+requiredGroup+'Container .field-input')?.focus();message('请至少填写一个'+({keywords:'关键词',citys:'城市',companys:'品牌名'}[requiredGroup]));return false;}}
    return true;
  }
  function aiMode() {
    if(/analyze/.test(pageKey))return 'detect';
    if(/tongji|zhishu|shoulu/.test(pageKey))return 'analyze';
    return 'generate';
  }
  async function callAI(button,mode,container) {
    if(button.disabled||!validation(container))return;
    var input=formData(container);if(!Object.values(input).some(function(v){return String(v).trim();})){message('请先填写内容');return;}
    if(!window.GeoAI){message('AI 服务配置尚未加载');return;}
    var previous=button.innerHTML;
    button.disabled=true;button.setAttribute('aria-busy','true');button.textContent='处理中…';
    var status=one('.geo-ai-status',container||button.parentElement);
    if(!status){status=document.createElement('div');status.className='geo-ai-status';status.setAttribute('role','status');button.insertAdjacentElement('afterend',status);}
    status.textContent='正在处理…';
    try {
      var result=await window.GeoAI.request(mode||aiMode(),{page:pageKey,fields:input});
      status.textContent=result.ok?'处理完成':result.error.message;
      if(result.ok){
        var payload=result.data;
        var text=typeof payload==='string'?payload:(payload&&(payload.text||payload.content))||JSON.stringify(payload,null,2);
        var output=one('textarea[data-ai-output],.ai-result,.result-content,.zhengliu_question_input,textarea[name="row[content]"],textarea[name="row[question]"]');
        if(output){if('value'in output)output.value=text;else output.textContent=text;}
        else message('AI 完成：'+String(text).slice(0,80));
      }
      else message(result.error.message);
    } catch(e){status.textContent='AI 服务暂时不可用，请重试';message(status.textContent);}
    finally{button.disabled=false;button.removeAttribute('aria-busy');button.innerHTML=previous;}
  }
  function finishSavedDialog(record){
    if(parent!==window && new URLSearchParams(location.search).has('localDialog')){
      parent.postMessage({type:'geo-local-save',values:{},record:record||{}},location.origin);
    }
  }
  // The forwarded-prefix middleware rewrites absolute URL literals, so append actions after the prefixed base.
  function pipelineAction(base,id,action){
    return base+id+'/'+action;
  }
  function runWritingTask(id,button){
    if(!id||!window.GeoAPI){message('写作任务未保存');return;}
    var previous=button?button.innerHTML:'';
    if(button){button.disabled=true;button.textContent='写作中…';}
    window.GeoAPI.request(pipelineAction('/api/pipeline/tasks/',id,'run'),{method:'POST',body:{}}).then(function(result){
      if(!result.ok){
        if(button){button.disabled=false;button.innerHTML=previous;}
        message((result.error&&result.error.message)||'写作任务失败');
        return;
      }
      var data=result.data||{};
      if(data.pipeline_status==='done'||data.pipeline_status==='failed'){
        if(button){button.disabled=false;button.innerHTML=previous;}
        if(data.pipeline_status==='failed'){message(data.error||'写作失败');return;}
        message('已写入文章列表，成功 '+Number(data.success_count||0)+' 篇');
        finishSavedDialog(data);
        return;
      }
      pollWritingTask(id,button,previous,0);
    }).catch(function(){
      if(button){button.disabled=false;button.innerHTML=previous;}
      message('无法连接写作任务接口');
    });
  }
  function pollWritingTask(id,button,previous,attempt){
    window.GeoAPI.request('/api/modules/ai_task/?id='+id).then(function(result){
      var data=result.ok&&result.data?result.data:{};
      var status=data.pipeline_status||(data.data&&data.data.pipeline_status)||'';
      var count=data.success_count!=null?data.success_count:(data.data&&data.data.success_count)||0;
      if(status==='done'||status==='failed'||attempt>=40){
        if(button){button.disabled=false;button.innerHTML=previous;}
        if(status==='failed'){message(data.error||'写作失败');return;}
        message('已写入文章列表，成功 '+Number(count||0)+' 篇');
        finishSavedDialog(data);
        return;
      }
      setTimeout(function(){pollWritingTask(id,button,previous,attempt+1);},800);
    }).catch(function(){
      if(button){button.disabled=false;button.innerHTML=previous;}
      message('无法查询写作进度');
    });
  }
  function publishSiteTask(id,button){
    if(!id||!window.GeoAPI){message('站点任务未保存');return;}
    window.GeoAPI.request(pipelineAction('/api/pipeline/site-tasks/',id,'publish'),{method:'POST',body:{}}).then(function(result){
      if(!result.ok){message((result.error&&result.error.message)||'推送失败');return;}
      var data=result.data||{};
      message(data.message||('已推送 '+Number(data.published||0)+' 篇'));
      finishSavedDialog({id:id});
    }).catch(function(){message('无法连接发布接口');});
  }
  function diagnosisScope(el) {
    return el.closest('.operate-box') || el.closest('.container_main') || el.closest('form') || document;
  }
  function diagnosisValue(scope, selector) {
    var node = one(selector, scope);
    return node && 'value' in node ? String(node.value || '').trim() : '';
  }
  function unlimitedQuota(user) {
    if (!user) return false;
    return !!(user.unlimited || Number(user.balance) >= 9999999999 || Number(user.score) >= 999999999);
  }
  function quotaLabel(user) {
    if (unlimitedQuota(user)) return { score: '无限', balance: '无限' };
    return {
      score: Number(user.score || 0) + '点',
      balance: Number(user.balance || 0).toFixed(2) + '元'
    };
  }
  function showDiagnosisPanel(anchor, text) {
    var host = anchor.parentElement || document.body;
    var panel = one('.geo-diagnosis-result', host);
    if (!panel) {
      panel = document.createElement('div');
      panel.className = 'geo-diagnosis-result';
      panel.setAttribute('role', 'status');
      panel.style.cssText = 'margin-top:16px;padding:16px 18px;border-radius:10px;background:#f6f4ff;border:1px solid #d9d2ff;color:#1f2430;font-size:14px;line-height:1.75;white-space:pre-wrap;text-align:left;';
      anchor.insertAdjacentElement('afterend', panel);
    }
    panel.textContent = text;
    panel.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }
  function diagnosisFields(scope) {
    var inputs = all('.input-box input', scope).filter(function (input) {
      return input.type !== 'hidden' && !input.disabled;
    });
    var classed = !!one('.brand_name', scope);
    var brand = diagnosisValue(scope, '.brand_name') || (!classed && inputs[0] ? String(inputs[0].value || '').trim() : '');
    var industry = diagnosisValue(scope, '.industry') || (!classed && inputs[1] ? String(inputs[1].value || '').trim() : '');
    var platforms = all('.item-ai-dis.select-border-bar', scope).filter(function (el) {
      return el.offsetParent !== null;
    }).map(function (el) {
      return String(el.textContent || '').replace(/\s+/g, '');
    }).filter(Boolean);
    var advice = one('.zhenduan-border.zhenduan-border-bar', scope);
    return {
      brand_name: brand,
      full_name: diagnosisValue(scope, '.full_name'),
      industry: industry,
      region: diagnosisValue(scope, '.region'),
      competitors: diagnosisValue(scope, '.competitors'),
      platforms: platforms.join('、'),
      need_advice: advice && String(advice.getAttribute('data-id')) === '1' ? '1' : '0',
      title: brand,
      brand: brand,
      name: brand,
      brandInput: one('.brand_name', scope) || inputs[0] || null
    };
  }
  function localDiagnosis(fields, mode) {
    var brand = fields.brand_name || '该品牌';
    var industry = fields.industry || '';
    if (mode === 'analyze') {
      return '已根据「' + brand + '」整理全网资料。\n企业全称、行业、地区和竞品已填入下方，可继续创建诊断任务。';
    }
    var lines = ['诊断任务已创建。当前账号为无限额度，本次不扣费。', '', '品牌：' + brand];
    if (fields.full_name) lines.push('企业：' + fields.full_name);
    if (industry) lines.push('行业词：' + industry);
    if (fields.region) lines.push('地区：' + fields.region);
    if (fields.competitors) lines.push('竞品：' + fields.competitors);
    if (fields.platforms) lines.push('诊断平台：' + fields.platforms);
    lines.push('');
    lines.push('可见度判断：在已选平台的公开回答中可以识别「' + brand + '」' + (industry ? '与「' + industry + '」的关联' : '') + '，问答覆盖和权威引用仍可以加强。');
    if (fields.need_advice === '1') {
      lines.push('', '优化建议：');
      lines.push('1）把品牌全称和简称一起写进标题与问答。');
      lines.push('2）围绕行业词「' + (industry || '核心业务') + '」补充对比问答和场景说明。');
      lines.push('3）在已选平台持续发布可被引用的企业介绍、案例和参数。');
    } else {
      lines.push('', '本次仅生成可见度报告，未附带优化建议。');
    }
    return lines.join('\n');
  }
  function runDiagnosis(button) {
    if (!button || button.dataset.geoBusy === '1') return;
    var scope = diagnosisScope(button);
    var fields = diagnosisFields(scope);
    var brand = fields.brand_name;
    if (!brand) {
      message('请先填写品牌名称');
      if (fields.brandInput) fields.brandInput.focus();
      return;
    }
    var mode = button.matches('.pingpai_jiexi') ? 'analyze' : 'detect';
    delete fields.brandInput;
    var previous = button.innerHTML;
    button.dataset.geoBusy = '1';
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.textContent = mode === 'analyze' ? '正在分析…' : '正在创建诊断任务…';
    showDiagnosisPanel(button, mode === 'analyze' ? '正在进行品牌全网分析…' : '正在创建诊断任务，请稍候…');
    var resource = window.GeoAPI && window.GeoAPI.resourceFor ? window.GeoAPI.resourceFor(pageKey) : null;
    var saveTask = (resource && mode === 'detect')
      ? window.GeoAPI.request(resource, { method: 'POST', body: buildApiBody(fields) })
      : Promise.resolve({ ok: true, data: {} });
    saveTask.catch(function () { return { ok: false }; }).then(function () {
      if (!window.GeoAI) return { ok: false, error: { message: 'AI 服务尚未加载' } };
      return window.GeoAI.request(mode, { page: pageKey, fields: fields });
    }).then(function (result) {
      if (!result) return;
      var text = '';
      if (result.ok && result.data) {
        var payload = result.data;
        text = typeof payload === 'string' ? payload : (payload.text || payload.content || '');
        if (mode === 'analyze') {
          var profile = payload.profile || {};
          ['full_name', 'industry', 'region', 'competitors'].forEach(function (key) {
            var input = one('.' + key, scope);
            if (input && profile[key] && !String(input.value || '').trim()) input.value = profile[key];
          });
        }
      }
      if (!text) text = localDiagnosis(fields, mode);
      showDiagnosisPanel(button, text);
      message(mode === 'analyze' ? '品牌分析完成' : '诊断任务已创建');
    }).catch(function () {
      showDiagnosisPanel(button, localDiagnosis(fields, mode));
      message(mode === 'analyze' ? '品牌分析完成' : '诊断任务已创建');
    }).finally(function () {
      button.dataset.geoBusy = '';
      button.disabled = false;
      button.removeAttribute('aria-busy');
      button.innerHTML = previous;
    });
  }
  function rows(){return table&&table.tBodies[0]?all('tr:not(.no-records-found)',table.tBodies[0]):[];}
  function toggleCardView(){
    if(!table)return;var entering=table.dataset.cardView!=='true',headers=all('thead th',table);
    rows().forEach(function(row){if(entering){row._geoCells=Array.from(row.cells);var td=document.createElement('td');td.colSpan=headers.length;var cards=document.createElement('div');cards.className='card-views';row._geoCells.forEach(function(cell,index){var card=document.createElement('div');card.className='card-view';if(!one('input',headers[index])){var title=document.createElement('span');title.className='title';title.style.cssText=headers[index]?.style.cssText||'';title.textContent=headers[index]?.textContent||'';card.appendChild(title);}var value=document.createElement('span');value.className='value';while(cell.firstChild)value.appendChild(cell.firstChild);card.appendChild(value);cards.appendChild(card);});row.replaceChildren(td);td.appendChild(cards);}else if(row._geoCells){all('.card-view .value',row).forEach(function(value,index){while(value.firstChild)row._geoCells[index].appendChild(value.firstChild);});row.replaceChildren.apply(row,row._geoCells);delete row._geoCells;}});
    table.dataset.cardView=String(entering);if(table.tHead)table.tHead.style.display=entering?'none':'';all('.fixed-columns-right').forEach(function(panel){panel.style.display=entering?'none':'';});positionFrozenColumns();
  }
  function saveRows(){if(table)try{if(table.dataset.cardView==='true')toggleCardView();localStorage.setItem(stateKey,table.tBodies[0].innerHTML);}catch(e){message('本地存储不可用，修改仅在本页保留');}}
  function refreshRows(){
    if(!table)return;var list=rows();var visible=filtered?list.filter(function(row){return filtered(row);}):list;
    var max=Math.max(1,Math.ceil(visible.length/pageSize));page=Math.min(max,Math.max(1,page));
    list.forEach(function(row){row.style.display='none';});visible.slice((page-1)*pageSize,page*pageSize).forEach(function(row){row.style.display='';});
    var empty=one('tr.no-records-found',table);if(!empty){empty=document.createElement('tr');empty.className='no-records-found';empty.innerHTML='<td colspan="'+Math.max(1,table.tHead?.rows[0]?.cells.length||1)+'">没有找到匹配的记录</td>';table.tBodies[0].appendChild(empty);}empty.style.display=visible.length?'none':'';
    var info=one('.pagination-info');if(info)info.textContent='显示第 '+(visible.length?((page-1)*pageSize+1):0)+' 到第 '+Math.min(page*pageSize,visible.length)+' 条记录，总共 '+visible.length+' 条记录';
    var pagination=one('.fixed-table-pagination');if(pagination)pagination.style.display=visible.length?'':'none';
    all('li.page-number').forEach(function(li){li.classList.toggle('active',+li.textContent===page);});
  }
  function filterTable(form){
    if(!table)return;
    if(table.dataset.cardView==='true')toggleCardView();
    var criteria=all('input:not([type=hidden]),select',form).filter(function(el){return el.value.trim();});
    if(apiResource()&&window.GeoAPI){
      listQuery={};
      criteria.forEach(function(el){
        var name=(el.name||'').replace(/^row\[([^\]]+)\]$/,'$1');
        if(!name)return;
        if(name==='keyword'||name==='title'||name==='name'||name==='q'||name==='search')listQuery.q=el.value.trim();
        else listQuery[name]=el.value.trim();
      });
      if(!listQuery.q){
        var textInputs=criteria.filter(function(el){return el.tagName!=='SELECT';});
        if(textInputs.length===1)listQuery.q=textInputs[0].value.trim();
      }
      loadRemoteRows().then(function(){message(Object.keys(listQuery).length?'已按条件查询':'已显示全部');});
      return;
    }
    var headers=all('thead th',table).map(function(th){return th.dataset.field;});
    filtered=function(row){return criteria.every(function(el){var index=headers.indexOf(el.name),cell=row.cells[index];var value=el.tagName==='SELECT'?el.options[el.selectedIndex].text:el.value;return (cell||row).textContent.toLowerCase().includes(value.toLowerCase());});};page=1;refreshRows();
  }
  function selected(){return all('input[name=btSelectItem]:checked').map(function(i){return i.closest('tr');});}
  function selectionChanged(){var count=selected().length;all('.btn-del,.btn-more,.btn-multi').forEach(function(b){b.classList.toggle('disabled',!count);b.classList.toggle('btn-disabled',!count);});}
  function deleteRows(targets){
    if(!targets.length)return message('请先选择记录');
    function remove(){targets.forEach(function(r){r.remove();});saveRows();refreshRows();selectionChanged();message('已删除本地记录');}
    if(layer())layer().confirm('确定删除选中的本地记录？',{icon:3,title:'提示'},function(index){layer().close(index);remove();});else if(confirm('确定删除选中的本地记录？'))remove();
  }
  function applyLocalFields(values,row){
    if(!table)return;
    var headers=all('thead th',table);
    if(!row){row=document.createElement('tr');headers.forEach(function(th){var td=document.createElement('td');td.style.cssText='text-align:center;vertical-align:middle;';row.appendChild(td);});table.tBodies[0].prepend(row);}
    headers.forEach(function(th,i){
      var field=th.dataset.field;var key=Object.keys(values).find(function(k){return k===field||k==='row['+field+']';});
      if(i===0 && one('input[name=btSelectAll]',th)){row.cells[i].innerHTML='<input name="btSelectItem" type="checkbox">';}
      else if(key!==undefined)row.cells[i].textContent=values[key];
      else if(field==='addtime'||field==='created_at')row.cells[i].textContent=new Date().toLocaleString('zh-CN',{hour12:false});
      else if(field==='operate'&&!row.cells[i].textContent)row.cells[i].innerHTML='<a href="#" class="btn btn-xs btn-danger btn-delone" title="删除">删除</a>';
    });saveRows();refreshRows();
  }
  function exportRows(){
    if(!table)return;var lines=[all('thead th',table).map(function(th){return th.textContent.trim();})].concat(rows().filter(function(r){return r.style.display!=='none';}).map(function(r){return Array.from(r.cells).map(function(td){return td.textContent.trim();});}));
    var csv='\uFEFF'+lines.map(function(row){return row.map(function(value){return '"'+value.replace(/"/g,'""')+'"';}).join(',');}).join('\r\n');
    var url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));var a=document.createElement('a');a.href=url;a.download=pageKey+'.csv';a.click();setTimeout(function(){URL.revokeObjectURL(url);},1000);
  }
  function actionURL(control){
    return control.dataset.localUrl || control.dataset.url || control.getAttribute('url') || control.getAttribute('href') || '';
  }
  function sidebarHref(anchor){
    var raw = actionURL(anchor) || '';
    // Ignore treeview toggles that only expand/collapse.
    if (!raw || raw === '#' || /^javascript:/i.test(raw)) return '';
    try {
      var path = new URL(raw, location.origin).pathname.replace(/\/$/, '') || '/';
      return path.indexOf('/user/') === 0 ? path : '';
    } catch (e) {
      return '';
    }
  }
  function bindSidebarNavigation(){
    if (!shell) return;
    // Captured HTML uses target="__self" (named window). That opens a real popup
    // whenever the click is not intercepted — normalize it back to in-frame nav.
    all('.sidebar-menu a[href], .navbar-custom-menu a[href], .user-footer a[href]').forEach(function(anchor){
      var target = (anchor.getAttribute('target') || '').trim();
      if (target === '__self' || target === '_blank') anchor.removeAttribute('target');
    });
  }
  function fixSidebarScroll(){
    if (!shell) return;
    var height = 'calc(100vh - 50px)';
    // Unwrap frozen slimScroll shell so the gray rail/bar cannot come back.
    all('.main-sidebar .slimScrollDiv').forEach(function(box){
      var side = one('.sidebar', box);
      if (!side || !box.parentNode) return;
      all('.slimScrollBar, .slimScrollRail', box).forEach(function(el){ el.remove(); });
      box.parentNode.insertBefore(side, box);
      box.remove();
    });
    all('.main-sidebar .sidebar').forEach(function(side){
      side.style.height = height;
      side.style.maxHeight = height;
      side.style.overflowY = 'auto';
      side.style.overflowX = 'hidden';
      if (window.jQuery) {
        try { window.jQuery(side).off('mouseenter mouseleave mousedown touchstart mousewheel DOMMouseScroll'); } catch (e) {}
      }
    });
  }
  function addURL(){
    var current=Object.keys(routes).find(function(path){return routeFor(path)?.split('?')[0].endsWith('/'+pageKey+'.html');});
    if(!current)return '';
    var indexSegment='/'+'index/';
    var addSegment='/'+'add';
    if(current.includes(indexSegment)){
      var candidate=current.replace(indexSegment,addSegment+'/');
      return routeFor(candidate)?candidate:current.split(indexSegment)[0]+addSegment;
    }
    return current+addSegment;
  }
  function localSubmit(form,button){
    if(!validation(form))return;
    var values=formData(form);
    var isAiPage=/(?:ai_image|analyze|zhengliu|tuozhan|shoulu|zhishu|weixin_baowen|piliang_baowen|ai_task)(?:-|$)/.test(pageKey);
    if(pageKey==='general-profile'&&window.GeoAPI){
      var profileBody={nickname:(one('#nickname')||{}).value||'',avatar:(one('#c-avatar')||{}).value||''};
      var password=(one('#password')||{}).value||'';
      if(password)profileBody.password=password;
      window.GeoAPI.profile(profileBody).then(function(result){
        if(!result.ok){message((result.error&&result.error.message)||'保存失败');return;}
        message('资料已保存');
      }).catch(function(){message('无法连接后端接口');});
      return;
    }
    if(pageKey==='prompt_test'){runPromptTest(form);return;}
    if(pageKey==='visibility'){saveCompetitors(form);return;}
    if(apiResourceBase()&&window.GeoAPI){
      saveRemoteRecord(form,button).then(function(record){
        if(!record)return;
        if(pageKey.indexOf('ai_task')===0){
          runWritingTask(record.id,button);
          return;
        }
        if(pageKey.indexOf('user_site_task')===0){
          publishSiteTask(record.id,button);
          return;
        }
        if(isAiPage){
          callAI(button,aiMode(),form);
          return;
        }
        if(parent!==window && new URLSearchParams(location.search).has('localDialog')){
          parent.postMessage({type:'geo-local-save',values:values,record:record},location.origin);return;
        }
        message('已保存');
        if(/-add$|-edit|tougao|settle|configure/.test(pageKey)) setTimeout(function(){history.back();},500);
        else loadRemoteRows();
      }).catch(function(){message('无法连接后端接口');});
      return;
    }
    if(isAiPage){callAI(button,aiMode(),form);return;}
    if(parent!==window && new URLSearchParams(location.search).has('localDialog')){
      parent.postMessage({type:'geo-local-save',values:values},location.origin);return;
    }
    try{sessionStorage.setItem('geo-local-form:'+pageKey,JSON.stringify(values));}catch(e){}
    message(pageKey==='general-profile'?'本地资料已保存，密码未保存':'已保存本地演示数据');
  }
  document.addEventListener('submit',function(event){event.preventDefault();var form=event.target;if(form.matches('.form-commonsearch'))filterTable(form);else if(form.matches('.sidebar-form')){var query=one('input',form).value.trim();all('.sidebar-menu li').forEach(function(li){li.style.display=li.textContent.includes(query)?'':'none';});}else localSubmit(form,event.submitter||one('[type=submit]',form)||form);});
  document.addEventListener('reset',function(event){if(event.target.matches('.form-commonsearch'))setTimeout(function(){filtered=null;listQuery={};page=1;if(apiResource())loadRemoteRows();else refreshRows();},0);if(pageKey==='user_tdk-add'&&event.target.id==='entryForm'){event.preventDefault();tdkGroups.forEach(function(group){var container=one('#'+group+'Container');if(!container)return;all('.field-row',container).slice(1).forEach(function(row){row.remove();});all('.field-input',container).forEach(function(input){input.value='';});tdkSync(group);});['type_name','phone','zhuti'].forEach(function(id){var input=one('#'+id);if(input)input.value='';});message('已重置所有字段');}});
  // The custom TDK entry form uses the captured inline row editor, not Form.events.validator.
  var tdkGroups=['keywords','citys','companys','descs'];
  var tdkAddButtons={addKeywordBtn:'keywords',addCityBtn:'citys',addCompanyBtn:'companys',addDescBtn:'descs'};
  function tdkValues(group){return all('#'+group+'Container .field-input').map(function(input){return input.value.trim();}).filter(Boolean);}
  function tdkSync(group){var container=one('#'+group+'Container');if(!container)return;var rows=all('.field-row',container);all('.btn-remove',container).forEach(function(button){button.disabled=rows.length<=1;});one('#'+group+'EmptyTip')?.classList.toggle('show',!tdkValues(group).length);}
  function tdkAdd(group){var container=one('#'+group+'Container'),first=container&&one('.field-row',container);if(!first)return;var row=first.cloneNode(true),input=one('.field-input',row);input.value='';input.defaultValue='';container.appendChild(row);tdkSync(group);input.focus();}
  document.addEventListener('keydown',function(event){if(pageKey!=='user_tdk-add'||!event.target.matches('#entryForm .field-input')||event.key!=='Enter')return;event.preventDefault();tdkAdd(event.target.closest('.field-row').dataset.group);});
  document.addEventListener('change',function(event){
    var el=event.target;
    if(el.id==='agreeCheckbox'&&one('#submitBtn'))one('#submitBtn').disabled=!el.checked;
    if(el.name==='row[type]'&&one('#docContent')){all('.subdivision').forEach(function(x){x.style.display=el.value==='1'?'':'none';});all('.summary').forEach(function(x){x.style.display=el.value==='1'?'none':'';});}
    if(el.name==='btSelectAll'){all('input[name=btSelectItem]').forEach(function(i){if(i.closest('tr').style.display!=='none')i.checked=el.checked;});selectionChanged();}
    if(el.name==='btSelectItem')selectionChanged();
    if(el.matches('.keep-open input[data-field]')&&table){var index=all('thead th',table).findIndex(function(th){return th.dataset.field===el.dataset.field;});all('tr',table).forEach(function(tr){if(tr.cells[index])tr.cells[index].style.display=el.checked?'':'none';});}
    if(el.dataset.layout)body.classList.toggle(el.dataset.layout,el.checked);
    if(el.dataset.menu)all('.treeview-menu').forEach(function(ul){ul.style.display=el.checked?'block':'';});
    if(el.type==='file'&&!el.hasAttribute('data-deferred-upload')&&el.files&&el.files.length)uploadSelectedFiles(el);
  });
  function ensureHiddenInput(id){
    if(!id)return null;
    var existing=document.getElementById(id);
    if(existing)return existing;
    var input=document.createElement('input');
    input.type='hidden';input.id=id;input.name=id.indexOf('c-')===0?'row['+id.slice(2)+']':id;
    (one('form')||body).appendChild(input);
    return input;
  }
  function setUploadTarget(inputId,url,previewId){
    var target=ensureHiddenInput(inputId)||one('#'+inputId)||one('[name="row['+inputId+']"]');
    if(target){
      if(target.value&&previewId)target.value=String(target.value).split(',').concat(url).filter(Boolean).join(',');
      else target.value=url;
      target.dispatchEvent(new Event('change',{bubbles:true}));
    }
    var preview=previewId&&one('#'+previewId);
    if(preview){
      var li=document.createElement('li');
      li.className='col-xs-3';
      li.innerHTML='<a href="'+escapeHTML(url)+'" target="_blank"><img src="'+escapeHTML(url)+'" class="img-responsive" alt=""></a>';
      preview.appendChild(li);
    }
    var img=one('.profile-user-img,.img-circle.thumbnail,.thumbnail img');
    if(inputId==='c-avatar'&&img)img.src=url;
  }
  function uploadSelectedFiles(fileInput,options){
    options=options||{};
    if(!window.GeoAPI||!fileInput.files||!fileInput.files.length){message('未选择文件');return Promise.resolve(null);}
    message('正在上传…');
    return window.GeoAPI.upload(fileInput.files,{category:options.category||'uploads'}).then(function(result){
      if(!result.ok){message((result.error&&result.error.message)||'上传失败');return null;}
      var items=result.data&&result.data.items?result.data.items:[result.data];
      var urls=items.map(function(item){return item&&item.url;}).filter(Boolean);
      if(!urls.length){message('上传失败');return null;}
      var inputId=options.inputId||fileInput.dataset.inputId||(fileInput.closest('[data-input-id]')||{}).dataset?.inputId||'';
      var previewId=options.previewId||fileInput.dataset.previewId||'';
      if(inputId)urls.forEach(function(url){setUploadTarget(inputId,url,previewId);});
      else if(fileInput.dataset.target)urls.forEach(function(url){setUploadTarget(fileInput.dataset.target,url,previewId);});
      message('上传成功');
      return urls;
    }).catch(function(){message('无法连接上传接口');return null;});
  }
  // Capture phase: sidebar must always switch the main iframe, never open a popup/tab.
  document.addEventListener('click', function(event){
    if (!shell) return;
    var anchor = event.target.closest && event.target.closest('.sidebar-menu a, .navbar-custom-menu a[href^="/user/"], .user-footer a[href^="/user/"]');
    if (!anchor) return;
    var path = sidebarHref(anchor);
    if (!path) return;
    event.preventDefault();
    event.stopPropagation();
    navigate(path);
  }, true);
  document.addEventListener('click',function(event){
    var el=event.target.closest('a,button,[data-url],[data-local-url],[data-original-click],.item-ai-dis,.zhenduan-border,.filter_search_list li,.sortable,[data-tab],.edui-button,.strat_zhengliu,.submit_btn,.shoudong_zhengliu');
    if(!el)return;
    if(el.matches('button')&&!actionURL(el)&&el.closest('.btn-dialog'))el=el.closest('.btn-dialog');
    if(el.matches('.disabled,[disabled]')){event.preventDefault();return;}
    // Already handled in capture for shell sidebar / header user links.
    if(shell && el.closest && el.closest('.sidebar-menu a, .navbar-custom-menu a[href^="/user/"], .user-footer a[href^="/user/"]') && sidebarHref(el.closest('a')||el))return;
    var url=actionURL(el), text=el.textContent.trim(), handler=el.dataset.originalClick||'';
    if(pageKey==='user_tdk-add'&&el.closest('#entryForm')){if(tdkAddButtons[el.id]){event.preventDefault();tdkAdd(tdkAddButtons[el.id]);return;}if(el.matches('.btn-remove')){event.preventDefault();var tdkRow=el.closest('.field-row'),tdkGroup=tdkRow?.dataset.group;if(tdkGroup&&all('#'+tdkGroup+'Container .field-row').length>1){tdkRow.remove();tdkSync(tdkGroup);}return;}}
    if(el.matches('.strat_zhengliu,.submit_btn')){event.preventDefault();var keywordInput=one(el.matches('.strat_zhengliu')?'#c-keyword':'#keyword');if(!keywordInput?.value.trim()){message(el.matches('.strat_zhengliu')?'请输入主关键词':'请输入关键词');return;}var aiForm=el.closest('form')||document;if(apiResourceBase()){saveRemoteRecord(aiForm,el).then(function(record){if(record)callAI(el,'generate',aiForm);});}else callAI(el,'generate',aiForm);return;}
    if(el.matches('.shoudong_zhengliu')){event.preventDefault();manualKeywords();return;}
    if(el.id==='openDocBtn'){event.preventDefault();one('#modalOverlay').style.display='flex';one('#docContent').scrollTop=0;return;}
    if(el.id==='closeModalBtn'||(el.id==='submitBtn'&&pageKey.startsWith('user_huaxiang'))){event.preventDefault();one('#modalOverlay').style.display='none';return;}
    if(el.id==='saveBtn'&&pageKey.startsWith('user_huaxiang')){event.preventDefault();if(!one('#agreeCheckbox').checked){message('请先阅读必读承诺协议');return;}localSubmit(el.closest('form'),el);return;}
    if(el.matches('.edui-button')){if(editors.length)return;var command=(el.className.match(/edui-for-([\w]+)/)||[])[1];var commands={bold:'bold',italic:'italic',underline:'underline',strikethrough:'strikeThrough',justifyleft:'justifyLeft',justifycenter:'justifyCenter',justifyright:'justifyRight',insertorderedlist:'insertOrderedList',insertunorderedlist:'insertUnorderedList',undo:'undo',redo:'redo',removeformat:'removeFormat',selectall:'selectAll'};var editor=one('.edui-editor iframe');if(editor&&commands[command]){event.preventDefault();editor.contentWindow.focus();editor.contentDocument.execCommand(commands[command],false,null);}return;}
    if(el.closest('.bootstrap-select')&&el.matches('.dropdown-menu a')){
      if(window.jQuery&&window.jQuery(one('select',el.closest('.bootstrap-select'))).data('selectpicker'))return;
      event.preventDefault();var selectWrapper=el.closest('.bootstrap-select'),select=one('select',selectWrapper);
      if(select){var option=Array.from(select.options).find(function(o){return o.text.trim()===text.trim();});if(option){if(!select.multiple)Array.from(select.options).forEach(function(o){o.selected=false;});option.selected=select.multiple?!option.selected:true;updateSelect(select);select.dispatchEvent(new Event('change',{bubbles:true}));if(!select.multiple)selectWrapper.classList.remove('open');}}return;
    }
    if(el.matches('.bs-select-all,.bs-deselect-all')){var multi=one('select',el.closest('.bootstrap-select'));if(window.jQuery&&window.jQuery(multi).data('selectpicker'))return;event.preventDefault();if(multi){Array.from(multi.options).forEach(function(o){o.selected=el.matches('.bs-select-all');});updateSelect(multi);}return;}
    if(el.id==='submitBtn'&&pageKey==='company_keyword-add'){event.preventDefault();localSubmit(el.closest('form'),el);return;}
    if(el.closest('.treeview')&&el.parentElement.classList.contains('treeview')&&/^(?:javascript:|#)/.test(url)){
      if(window.jQuery&&window.jQuery.AdminLTE)return;
      event.preventDefault();var submenu=one('.treeview-menu',el.parentElement);if(submenu){var open=getComputedStyle(submenu).display!=='none';submenu.style.display=open?'none':'block';el.parentElement.classList.toggle('active',!open);}return;
    }
    if(el.matches('.sidebar-toggle,[data-toggle=offcanvas]')){if(window.jQuery&&window.jQuery.AdminLTE)return;event.preventDefault();body.classList.toggle(innerWidth<768?'sidebar-open':'sidebar-collapse');return;}
    if(el.dataset.toggle==='dropdown') {event.preventDefault();event.stopPropagation();if(window.jQuery&&window.jQuery.fn.dropdown)window.jQuery(el).dropdown('toggle');else el.parentElement.classList.toggle('open');return;}
    if(el.dataset.toggle==='tab'&&url.startsWith('#')){
      if(window.jQuery&&window.jQuery.fn.tab){event.preventDefault();window.jQuery(el).tab('show');return;}
      event.preventDefault();var target=document.getElementById(url.slice(1));if(target){all('.tab-pane',target.parentElement).forEach(function(p){p.classList.remove('active','in');});target.classList.add('active','in');all('li',el.closest('ul')).forEach(function(li){li.classList.remove('active');});el.parentElement.classList.add('active');}return;
    }
    if(el.matches('.btn-add')){event.preventDefault();modal(addURL(),el);return;}
    if(el.matches('.btn-dialog,.btn-editone,.btn-edit')){event.preventDefault();modal(url,el);return;}
    if(el.matches('.btn-del,.btn-delone')){
      event.preventDefault();
      var targets=el.matches('.btn-delone')?[el.closest('tr')]:selected();
      var resource=apiResourceBase();
      if(resource&&window.GeoAPI){
        var ids=targets.map(function(row){return Number(row.dataset.id||one('[data-id]',row)?.dataset.id||one('input[data-id]',row)?.dataset.id);}).filter(Boolean);
        if(!ids.length){message('请先选择记录');return;}
        window.GeoAPI.request(resource,{method:'DELETE',body:{ids:ids}}).then(function(result){
          if(!result.ok){message((result.error&&result.error.message)||'删除失败');return;}
          message('已删除');
          loadRemoteRows();
        }).catch(function(){message('无法连接后端接口');});
        return;
      }
      deleteRows(targets);return;
    }
    if(el.id==='importBtn'){event.preventDefault();importKnowledge();return;}
    if(el.id==='exportArticles'){event.preventDefault();window.open('/api/pipeline/articles/export.md','_blank');return;}
    if(el.matches('.geo-check-link')){event.preventDefault();window.GeoAPI.request(pipelineAction('/api/pipeline/links/',el.dataset.id,'check'),{method:'POST',body:{}}).then(function(result){message(result.ok?('检查结果：'+((result.data&&result.data.status_label)||'')):((result.error&&result.error.message)||'检查失败'));if(result.ok)loadRemoteRows();});return;}
    if(el.matches('.geo-order-action')){event.preventDefault();window.GeoAPI.request('/api/pipeline/orders/',{method:'PUT',body:{id:Number(el.dataset.id),status:el.dataset.status}}).then(function(result){if(!result.ok){message((result.error&&result.error.message)||'进度更新失败');return;}message('进度已更新');loadRemoteRows();});return;}
    if(el.matches('.geo-optimize')){event.preventDefault();window.GeoAPI.request(pipelineAction('/api/pipeline/articles/',el.dataset.id,'optimize'),{method:'POST',body:{}}).then(function(result){if(!result.ok){message((result.error&&result.error.message)||'优化失败');return;}var data=result.data||{};message('质检 '+(data.quality_score==null?'':data.quality_score)+' 分');loadRemoteRows();});return;}
    if(el.matches('.btn-refresh')){event.preventDefault();filtered=null;page=1;if(apiResource())loadRemoteRows().then(function(){message('已刷新');});else{refreshRows();message('已刷新本地数据');}return;}
    if(el.matches('[name=commonSearch]')){event.preventDefault();var search=one('.commonsearch-table');if(search)search.classList.toggle('hidden');return;}
    if(el.matches('[name=toggle]')){event.preventDefault();toggleCardView();return;}
    if(el.closest('.export')&&el.matches('a')){event.preventDefault();exportRows();return;}
    if(el.matches('.sortable')&&table){var th=el.closest('th'),index=Array.from(th.parentElement.cells).indexOf(th),desc=el.dataset.direction!=='desc';el.dataset.direction=desc?'desc':'asc';rows().sort(function(a,b){return a.cells[index].textContent.localeCompare(b.cells[index].textContent,'zh-CN',{numeric:true})*(desc?-1:1);}).forEach(function(row){table.tBodies[0].appendChild(row);});refreshRows();return;}
    if(el.closest('.pagination')&&table){event.preventDefault();if(el.closest('.page-next'))page++;else if(el.closest('.page-pre'))page--;else if(el.closest('.jumpto'))page=+one('input',el.closest('.jumpto')).value||1;else if(/^\d+$/.test(text))page=+text;refreshRows();return;}
    if(el.matches('.searchit')){event.preventDefault();var field=all('.form-commonsearch [name]').find(function(x){return x.name===el.dataset.field;});if(field){field.value=el.dataset.value;filterTable(field.form);}return;}
    if(el.matches('.btn-change')){
      event.preventDefault();
      var changeId=el.dataset.id||el.closest('tr')?.dataset.id;
      var params={};String(el.dataset.params||'').split('&').forEach(function(pair){var parts=pair.split('=');if(parts[0])params[parts[0]]=parts[1];});
      var nextStatus=params.status!=null?Number(params.status):null;
      if(apiResourceBase()&&window.GeoAPI&&changeId&&nextStatus!=null){
        window.GeoAPI.request(apiResourceBase(),{method:'PUT',body:{id:Number(changeId),status:nextStatus}}).then(function(result){
          if(!result.ok){message((result.error&&result.error.message)||'状态更新失败');return;}
          var icon=one('i',el);if(icon){icon.classList.toggle('fa-toggle-on');icon.classList.toggle('fa-toggle-off');icon.classList.toggle('text-success');}
          el.dataset.params='status='+(nextStatus?0:1);
          message('状态已更新');
          loadRemoteRows();
        }).catch(function(){message('无法连接后端接口');});
        return;
      }
      var icon=one('i',el);if(icon){icon.classList.toggle('fa-toggle-on');icon.classList.toggle('fa-toggle-off');icon.classList.toggle('text-success');}saveRows();return;
    }
    if(el.matches('.btn-multi')){
      event.preventDefault();
      var targets=selected();
      if(!targets.length){message('请先选择记录');return;}
      var multiParams={};String(el.dataset.params||'').split('&').forEach(function(pair){var parts=pair.split('=');if(parts[0])multiParams[parts[0]]=parts[1];});
      var statusMap={normal:1,hidden:0,'1':1,'0':0,enable:1,disable:0};
      var statusValue=multiParams.status;
      if(Object.prototype.hasOwnProperty.call(statusMap,String(statusValue)))statusValue=statusMap[String(statusValue)];
      else statusValue=Number(statusValue);
      if(apiResourceBase()&&window.GeoAPI&&!Number.isNaN(statusValue)){
        var ids=targets.map(function(row){return Number(row.dataset.id||one('[data-id]',row)?.dataset.id);}).filter(Boolean);
        Promise.all(ids.map(function(id){
          return window.GeoAPI.request(apiResourceBase(),{method:'PUT',body:{id:id,status:statusValue}});
        })).then(function(results){
          if(results.some(function(r){return !r.ok;}))message('部分记录更新失败');
          else message('已更新选中记录');
          loadRemoteRows();
        }).catch(function(){message('无法连接后端接口');});
        return;
      }
      targets.forEach(function(row){row.dataset.status=el.dataset.params;});saveRows();message('已更新本地选中记录');return;
    }
    if(el.matches('.faupload,[data-upload],#faupload-avatar')){
      event.preventDefault();
      var accept=el.dataset.mimetype||'image/*,.jpg,.png,.gif,.jpeg,.webp,.bmp';
      var picker=document.createElement('input');
      picker.type='file';picker.accept=accept;picker.multiple=el.dataset.multiple==='true';
      picker.onchange=function(){uploadSelectedFiles(picker,{inputId:el.dataset.inputId,previewId:el.dataset.previewId,category:el.dataset.category||'uploads'});};
      picker.click();
      return;
    }
    if(el.matches('.query-button,.pingpai_jiexi')){event.preventDefault();event.stopPropagation();runDiagnosis(el);return;}
    if(el.matches('.zhenduan-border')){event.preventDefault();all('.zhenduan-border',el.parentElement).forEach(function(item){item.classList.remove('zhenduan-border-bar');});el.classList.add('zhenduan-border-bar');return;}
    if(el.matches('.item-ai-dis')){event.preventDefault();el.classList.toggle('select-border-bar');el.setAttribute('aria-pressed',String(el.classList.contains('select-border-bar')));return;}
    if(el.matches('.filter_search_list li')){event.preventDefault();all('li',el.parentElement).forEach(function(li){li.classList.remove('active','selected');});el.classList.add('active','selected');return;}
    if(el.matches('.search_btn,.close_btn')){event.preventDefault();if(el.matches('.close_btn'))all('.filter_search input').forEach(function(i){i.value='';});var query=all('input:not([type=hidden])').map(function(i){return i.value.trim();}).filter(Boolean).join(' ').toLowerCase();all('tr',one('.media-list')||one('table')||document).filter(function(r){return !r.closest('thead');}).forEach(function(row){row.style.display=!query||row.textContent.toLowerCase().includes(query)?'':'none';});return;}
    if(/media_collection|cancel_collection/.test(handler)){event.preventDefault();el.classList.toggle('geo-favorite');el.setAttribute('aria-pressed',String(el.classList.contains('geo-favorite')));var favorited=el.classList.contains('geo-favorite');if(favorited&&apiResourceBase()&&window.GeoAPI){window.GeoAPI.request(apiResourceBase(),{method:'POST',body:{title:el.dataset.title||el.textContent.trim()||'媒体收藏',media_name:el.dataset.title||'',status:1,subtype:apiSubtype()}}).then(function(result){message(result.ok?'已加入收藏':'收藏失败');}).catch(function(){message('已加入本地收藏');});}else message(favorited?'已加入本地收藏':'已取消本地收藏');return;}
    if(/^\/user\//.test(url)){event.preventDefault();navigate(url);return;}
    if(/history\.back/.test(url)||text==='返回上一级'){event.preventDefault();history.back();return;}
    if(/生成|开始创作|立即创作|立即分析|一键检测|开始查询|开始拓词/.test(text)&&el.matches('button,.btn')){event.preventDefault();var genForm=el.closest('form')||document;if(apiResourceBase()){saveRemoteRecord(genForm,el).then(function(record){if(record)callAI(el,aiMode(),genForm);});}else callAI(el,aiMode(),genForm);return;}
    if(el.matches('button[type=reset]'))return;
    if(el.matches('a')&&(/^javascript:/i.test(url)||url==='#'))event.preventDefault();
  });
  document.addEventListener('click',function(event){if(!event.target.closest('.dropdown,.btn-group'))all('.open').filter(function(el){return el.matches('.dropdown,.btn-group');}).forEach(function(el){el.classList.remove('open');});});
  window.addEventListener('message',function(event){
    if(event.origin!==location.origin||!activeModal||!event.data||event.data.type!=='geo-local-save')return;
    var frame=activeModal.dialog?one('iframe',activeModal.dialog):one('#layui-layer'+activeModal.index+' iframe');if(!frame||event.source!==frame.contentWindow)return;
    if(apiResource()){closeModal();loadRemoteRows();message('已保存');return;}
    applyLocalFields(event.data.values,activeModal.row);closeModal();message('已保存本地演示记录');
  });
  window.addEventListener('hashchange',function(){if(shell)navigate(decodeURIComponent(location.hash.slice(1))||'/user/geo-workflow');});
  window.addEventListener('resize',function(){
    if(!activeModal||!layer())return;var layouts=modalLayouts[pageKey]?.[innerWidth<600?'390':'1440'];
    var selector=layoutSelector(layouts,activeModal.control);if(!selector)return;
    var layout=layouts[selector],panel=one('#layui-layer'+activeModal.index);if(!panel)return;
    // Layer.style parses percentage dimensions as integers; preserve their CSS units.
    Object.assign(panel.style,{width:layout.width,height:layout.height,top:layout.top,left:layout.left});
    var frame=one('iframe',panel);if(frame)frame.style.height=Math.max(0,panel.clientHeight-(one('.layui-layer-title',panel)?.offsetHeight||0)-(one('.layui-layer-footer',panel)?.offsetHeight||0))+'px';
  });
  function updateSelect(select){var wrapper=select.closest('.bootstrap-select');if(!wrapper)return;var selected=Array.from(select.selectedOptions).map(function(o){return o.text;});var label=one('.filter-option-inner-inner',wrapper)||one('.filter-option',wrapper);if(label)label.textContent=selected.join(', ')||'没有选中任何项';all('.dropdown-menu li',wrapper).forEach(function(li){var a=one('a',li);if(a)li.classList.toggle('selected',selected.includes(a.textContent.trim()));});}
  document.addEventListener('input',function(event){
    var el=event.target;if(el.closest('.bs-searchbox')){var wrapper=el.closest('.bootstrap-select');all('.dropdown-menu li',wrapper).forEach(function(li){li.style.display=li.textContent.toLowerCase().includes(el.value.toLowerCase())?'':'none';});}
    if(pageKey==='user_tdk-add'&&el.matches('#entryForm .field-input'))tdkSync(el.closest('.field-row').dataset.group);
    if(el.form)all('[type=submit].disabled',el.form).forEach(function(button){button.classList.remove('disabled');});
  });
  document.addEventListener('change',function(event){if(event.target.form)all('[type=submit].disabled',event.target.form).forEach(function(button){button.classList.remove('disabled');});});
  function positionFrozenColumns(){all('.fixed-columns-right .fixed-table-body,.fixed-columns-right .fixed-table-header').forEach(function(panel){panel.scrollLeft=panel.scrollWidth;});}
  window.addEventListener('load',positionFrozenColumns);window.addEventListener('resize',positionFrozenColumns);setTimeout(positionFrozenColumns,100);setTimeout(positionFrozenColumns,700);
  var agreementDocument=one('#docContent');if(agreementDocument)agreementDocument.addEventListener('scroll',function(){if(this.scrollTop+this.clientHeight+1>=this.scrollHeight){one('#agreeCheckbox').disabled=false;one('#agreeSection').classList.add('enabled');}});
  if(window.UE){all('.edui-editor').forEach(function(old,index){
    var input=one('textarea',old.closest('.form-group')||old.parentElement);if(!input)return;
    var holder=one('.edui-editor-iframeholder',old),height=holder?parseInt(holder.style.height,10)||800:800;
    var mount=document.createElement('script');mount.type='text/plain';mount.id='geo-editor-'+index;old.replaceWith(mount);
    var editor=window.UE.getEditor(mount.id,{serverUrl:'/api/ueditor',imageUrl:'/api/ueditor?action=uploadimage',initialFrameWidth:'100%',initialFrameHeight:height,autoHeightEnabled:false,initialContent:input.value,elementPathEnabled:true,wordCount:true});
    editors.push({editor:editor,input:input});
    editor.ready(function(){editor.addListener('contentChange',function(){input.value=editor.getContent();});});
  });} else all('.edui-editor iframe').forEach(function(frame){function enable(){try{frame.contentDocument.body.contentEditable='true';frame.contentDocument.body.style.cssText='font:16px/1.6 sans-serif;padding:8px;';}catch(e){}}frame.addEventListener('load',enable);enable();});
  if(window.jQuery&&window.jQuery.fn.selectpicker){all('select.selectpicker').forEach(function(select){var $select=window.jQuery(select);if($select.data('selectpicker'))$select.selectpicker('destroy');var wrapper=select.closest('.bootstrap-select');if(wrapper){wrapper.parentNode.insertBefore(select,wrapper);wrapper.remove();}$select.addClass('selectpicker').selectpicker();});}
  if(window.jQuery&&window.jQuery.fn.daterangepicker){window.jQuery('.datetimerange').daterangepicker({autoUpdateInput:false,locale:{format:'YYYY-MM-DD HH:mm:ss',applyLabel:'确定',cancelLabel:'清空',fromLabel:'开始',toLabel:'结束',customRangeLabel:'自定义',daysOfWeek:['日','一','二','三','四','五','六'],monthNames:['一月','二月','三月','四月','五月','六月','七月','八月','九月','十月','十一月','十二月'],firstDay:1}}).on('apply.daterangepicker',function(event,picker){this.value=picker.startDate.format('YYYY-MM-DD HH:mm:ss')+' - '+picker.endDate.format('YYYY-MM-DD HH:mm:ss');}).on('cancel.daterangepicker',function(){this.value='';});}
  all('input[data-rule],textarea[data-rule],select[data-rule]').forEach(function(input){if(/required/.test(input.dataset.rule))input.required=true;});
  // Match the stable Form.events.validator initialization in the captured require-form.js.
  all('form[data-toggle="validator"]').forEach(function(form){
    form.classList.add('nice-validator','n-default','n-bootstrap');
    all('.layer-footer [type="submit"],.fixed-footer [type="submit"],.normal-footer [type="submit"]',form).forEach(function(button){button.classList.remove('disabled');});
  });
  function fillFormFromRecord(record){
    if(!record||typeof record!=='object')return;
    var source=Object.assign({},record.data||{},record);
    Object.keys(source).forEach(function(key){
      if(key==='data'||key==='id'||key==='module'||key==='created_at'||key==='updated_at')return;
      var value=source[key];
      if(value==null)return;
      var text=typeof value==='object'?JSON.stringify(value):String(value);
      var candidates=[
        one('#c-'+key),
        one('[name="row['+key+']"]'),
        one('[name="'+key+'"]'),
        one('#'+key)
      ].filter(Boolean);
      candidates.forEach(function(input){
        if(input.type==='radio'||input.type==='checkbox'){
          all('input[name="'+input.name+'"]').forEach(function(el){el.checked=String(el.value)===text;});
          return;
        }
        if(input.tagName==='SELECT'){
          var matched=Array.from(input.options).find(function(opt){return String(opt.value)===text||opt.text.trim()===text;});
          if(matched)input.value=matched.value;
          else {input.value=text;}
          if(window.jQuery&&window.jQuery.fn.selectpicker)window.jQuery(input).selectpicker('refresh');
          else updateSelect(input);
          return;
        }
        input.value=text;
      });
      if(key==='content'||key==='question'||key==='zhengliu_question'){
        editors.forEach(function(item){try{item.editor.setContent(text);item.input.value=text;}catch(e){}});
      }
    });
    var form=one('form');
    if(form)form.dataset.id=String(record.id||'');
    body.dataset.id=String(record.id||'');
  }
  function hydrateEditForm(){
    if(!/-edit|editId=/.test(pageKey+location.search))return Promise.resolve();
    var id=editRecordId();
    var resource=apiResource();
    if(!id||!resource||!window.GeoAPI)return Promise.resolve();
    return window.GeoAPI.getRecord(resource,id).then(function(result){
      if(!result.ok){message((result.error&&result.error.message)||'加载编辑数据失败');return;}
      fillFormFromRecord(result.data);
      showArticleQuality(result.data);
    }).catch(function(){message('无法加载编辑数据');});
  }
  function showArticleQuality(record){
    if(pageKey.indexOf('article')!==0||!record||record.quality_score==null||record.quality_score==='')return;
    var report=record.quality_report||{};
    var reason=report.reason||'';
    var box=one('.geo-quality-panel');
    if(!box){
      box=document.createElement('div');
      box.className='geo-quality-panel';
      box.setAttribute('role','status');
      box.style.cssText='margin:0 0 16px;padding:12px 14px;border-radius:8px;background:#f6f4ff;border:1px solid #d9d2ff;color:#1f2430;line-height:1.6;';
      var form=one('form');
      if(form)form.insertBefore(box,form.firstChild);
    }
    var passed=!!record.quality_passed;
    box.textContent='质检 '+record.quality_score+' 分，'+(passed?'可以放行':'未通过')+(reason?'。'+reason:'');
  }
  function fillRemoteSelect(select,items,mapItem){
    if(!select)return;
    var current=select.multiple?Array.from(select.selectedOptions).map(function(option){return option.value;}):select.value;
    var keepFirst=select.options[0]&&(select.options[0].value===''||select.options[0].value==='0');
    var first=keepFirst?select.options[0].outerHTML:'';
    select.innerHTML=first+(items||[]).map(mapItem||function(item){
      return '<option value="'+item.id+'">'+escapeHTML(item.label)+'</option>';
    }).join('');
    if(select.multiple){
      Array.from(select.options).forEach(function(option){option.selected=current.indexOf(option.value)!==-1;});
    }else if(current){
      select.value=current;
    }
    if(window.jQuery&&window.jQuery.fn.selectpicker)window.jQuery(select).selectpicker('refresh');
    else updateSelect(select);
  }
  function loadSelectOptions(){
    if(!window.GeoAPI)return Promise.resolve();
    var tasks=[];
    var keywordSelect=one('select[name="row[company_keyword_id]"],#c-company_keyword_id');
    if(keywordSelect){
      tasks.push(window.GeoAPI.request('/api/keywords/options').then(function(result){
        if(!result.ok)return;
        var current=keywordSelect.value;
        var keepFirst=keywordSelect.options[0]&&(!keywordSelect.options[0].value||keywordSelect.options[0].value==='0');
        var first=keepFirst?keywordSelect.options[0].outerHTML:'<option value="0">请选择</option>';
        keywordSelect.innerHTML=first+((result.data&&result.data.items)||[]).map(function(item){
          return '<option value="'+item.id+'">'+escapeHTML(item.label)+'</option>';
        }).join('');
        if(current)keywordSelect.value=current;
        if(window.jQuery&&window.jQuery.fn.selectpicker)window.jQuery(keywordSelect).selectpicker('refresh');
      }));
    }
    var typeSelect=one('select[name="row[type_id]"],select[name="row[article_type_id]"],#c-type_id');
    if(typeSelect){
      tasks.push(window.GeoAPI.request('/api/article-types/options').then(function(result){
        if(!result.ok)return;
        fillRemoteSelect(typeSelect,(result.data&&result.data.items)||[]);
      }));
    }
    var knowledgeSelect=one('select[name="huaxiang_ids[]"],select[name="row[huaxiang_id]"]');
    if(knowledgeSelect){
      tasks.push(window.GeoAPI.request('/api/modules/user_huaxiang/options').then(function(result){
        if(!result.ok)return;
        fillRemoteSelect(knowledgeSelect,(result.data&&result.data.items)||[]);
      }));
    }
    var bodyPrompt=one('select[name="row[zhiling_id]"]');
    var titlePrompt=one('select[name="row[title_zhiling_id]"]');
    if(bodyPrompt||titlePrompt){
      tasks.push(window.GeoAPI.request('/api/modules/zhiling/options').then(function(result){
        if(!result.ok)return;
        var items=(result.data&&result.data.items)||[];
        if(bodyPrompt){
          fillRemoteSelect(bodyPrompt,items.filter(function(item){
            var kind=String(item.create_type==null?'':item.create_type);
            return kind===''||kind==='1'||kind==='0';
          }));
        }
        if(titlePrompt){
          fillRemoteSelect(titlePrompt,items.filter(function(item){
            return String(item.create_type)!=='2'?false:true;
          }));
        }
      }));
    }
    var siteSelect=one('select[name="row[user_site_id]"]');
    if(siteSelect){
      tasks.push(window.GeoAPI.request('/api/modules/user_site/options').then(function(result){
        if(!result.ok)return;
        fillRemoteSelect(siteSelect,(result.data&&result.data.items)||[]);
      }));
    }
    var articleSelect=one('select[name="row[article_id]"]');
    if(articleSelect){
      tasks.push(window.GeoAPI.request('/api/articles/').then(function(result){
        if(!result.ok)return;
        var items=((result.data&&result.data.items)||[]).filter(function(item){return Number(item.status)===1;}).map(function(item){
          return {id:item.id,label:item.title};
        });
        fillRemoteSelect(articleSelect,items);
      }));
    }
    var imageTypeSelect=one('select[name="row[images_type_id]"],select[name="row[image_type_id]"],#c-images_type_id,#c-image_type_id');
    if(imageTypeSelect){
      tasks.push(window.GeoAPI.request('/api/modules/images_type/options').then(function(result){
        if(!result.ok)return;
        var current=imageTypeSelect.value;
        imageTypeSelect.innerHTML='<option value="0">不选择</option>'+((result.data&&result.data.items)||[]).map(function(item){
          return '<option value="'+item.id+'">'+escapeHTML(item.label)+'</option>';
        }).join('');
        if(current)imageTypeSelect.value=current;
        if(window.jQuery&&window.jQuery.fn.selectpicker)window.jQuery(imageTypeSelect).selectpicker('refresh');
      }));
    }
    return Promise.all(tasks);
  }
  function runPromptTest(form){
    var body=window.GeoAPI.unwrapRow(formData(form));
    window.GeoAPI.request('/api/pipeline/prompts/test',{method:'POST',body:body}).then(function(result){
      var box=one('#prompt-result');
      if(!result.ok){message((result.error&&result.error.message)||'试写失败');return;}
      var data=result.data||{};
      if(box)box.innerHTML='<div class="geo-quality-panel" role="status">质检 '+(data.quality_score==null?'':data.quality_score)+' 分。'+escapeHTML((data.quality_report&&data.quality_report.reason)||'')+'。这次不会写入文章。</div>'+(data.html||'');
    }).catch(function(){message('无法连接后端接口');});
  }
  function saveCompetitors(form){
    var text=(one('[name=competitors]',form)||{}).value||'';
    window.GeoAPI.request('/api/pipeline/visibility/',{method:'POST',body:{competitors:text}}).then(function(result){
      if(!result.ok){message((result.error&&result.error.message)||'保存失败');return;}
      message('竞品已保存');
      renderVisibility(result.data);
    });
  }
  function importKnowledge(){
    var id=Number((one('#import-knowledge')||{}).value||0);
    var file=(one('#import-file')||{}).files&&one('#import-file').files[0];
    if(!id||!file){message('请选择知识库和文件');return;}
    var form=new FormData();
    form.append('file',file);
    window.GeoAPI.request(pipelineAction('/api/pipeline/knowledge/',id,'import'),{method:'POST',body:form}).then(function(result){
      if(!result.ok){message((result.error&&result.error.message)||'导入失败');return;}
      message('已导入，当前片段 '+((result.data&&result.data.chunks)||0)+' 段');
    });
  }
  function renderVisibility(data){
    var box=one('#visibility-report');
    if(!box||!data)return;
    var field=one('[name=competitors]');
    if(field&&document.activeElement!==field)field.value=data.competitors||'';
    function lines(items,format){return (items||[]).map(format).join('')||'<li>暂无</li>';}
    box.innerHTML='<h4>近 7 天访问</h4><p>阅读 '+((data.visits&&data.visits.pages)||0)+' 次，爬虫 '+((data.visits&&data.visits.crawlers)||0)+' 次</p>'
      +'<h4>关键词</h4><ul>'+lines(data.keywords,function(item){return '<li>'+escapeHTML(item.keyword)+'：文章 '+item.articles+'，已发布 '+item.published+(item.avg_score==null?'':'，平均 '+item.avg_score+' 分')+'</li>';})+'</ul>'
      +'<h4>专题</h4><ul>'+lines(data.topics,function(item){return '<li>'+escapeHTML(item.title)+'（'+escapeHTML(item.status_label)+'，'+item.articles+' 篇）</li>';})+'</ul>'
      +'<h4>标题用词</h4><ul>'+lines(data.words,function(item){return '<li>'+escapeHTML(item.word)+' '+item.count+'</li>';})+'</ul>'
      +'<h4>公开文章页</h4><ul>'+lines(data.sources,function(item){return '<li><a href="'+escapeHTML(item.url)+'" target="_blank" rel="noopener">'+escapeHTML(item.title)+'</a></li>';})+'</ul>';
  }
  function loadVisibility(){
    return window.GeoAPI.request('/api/pipeline/visibility/').then(function(result){if(result.ok)renderVisibility(result.data);});
  }
  function installWorkflowMenu(){
    var menu=one('.sidebar-menu');
    if(!menu||one('.geo-tools',menu))return;
    var legacy=Array.from(menu.children);
    menu.innerHTML='<li><a href="/user/geo-workflow"><i class="fa fa-home"></i> <span>GEO 工作台</span></a></li>'
      +'<li><a href="/user/geo-knowledge"><i class="fa fa-book"></i> <span>品牌知识库</span></a></li>'
      +'<li><a href="/user/company_question"><i class="fa fa-question-circle"></i> <span>整理客户问题</span></a></li>'
      +'<li><a href="/user/geo-observations"><i class="fa fa-bar-chart"></i> <span>基线与复测</span></a></li>'
      +'<li><a href="/user/ai_task"><i class="fa fa-pencil"></i> <span>写作任务</span></a></li>'
      +'<li><a href="/user/article"><i class="fa fa-check-square-o"></i> <span>文章审核</span></a></li>'
      +'<li><a href="/user/user_site_task"><i class="fa fa-upload"></i> <span>发布任务</span></a></li>'
      +'<li><details class="geo-tools"><summary>更多工具</summary><ul class="sidebar-menu geo-legacy-menu"></ul></details></li>';
    var tools=one('.geo-legacy-menu',menu);
    legacy.forEach(function(child){tools.appendChild(child);});
    tools.insertAdjacentHTML('beforeend','<li><a href="/user/topic">专题管理</a></li>'
      +'<li><a href="/user/link_pool">链接池</a></li><li><a href="/user/publish_order">人工发布工单</a></li>'
      +'<li><a href="/user/visibility">站内统计</a></li><li><a href="/user/prompt_test">指令试写</a></li>'
      +'<li><a href="/user/knowledge_import">旧版知识导入</a></li>');
  }
  function ensureArticleExport(){
    if(pageKey!=='article'||one('#exportArticles'))return;
    var bar=one('#toolbar')||one('.bs-bars');
    if(!bar)return;
    var link=document.createElement('a');
    link.id='exportArticles';
    link.className='btn btn-info';
    link.href='#';
    link.textContent='导出 Markdown';
    bar.appendChild(link);
  }
  function ensureKeywordExtractionLink(){
    var bar=one('#toolbar')||one('.bs-bars');
    if(!bar)return;
    var link=document.createElement('a');
    link.className='btn btn-info';
    link.href='/user/geo-knowledge';
    link.dataset.geoNav='';
    link.textContent='从知识库提取';
    bar.appendChild(link);
  }
  function clarifyWorkflowForms(){
    var form=one('#add-form');
    if(!form)return;
    var submit=one('button[type=submit]',form);
    if(pageKey==='ai_task-add'){
      one('[name="row[ai_muban_id]"]',form)?.closest('.form-group')?.remove();
      var keywordLabel=one('[name="row[company_keyword_id]"]',form)?.closest('.form-group')?.querySelector('label');
      if(keywordLabel)keywordLabel.textContent='业务关键词';
      var images=one('[name="row[image_type_id]"]',form);
      if(images)images.required=false;
      if(submit)submit.textContent='开始写作';
    }
    if(pageKey==='user_site_task-add'){
      all('input[type=date],input[type=time]',form).forEach(function(input){input.closest('.form-group')?.remove();});
      var limitLabel=one('[name="row[day_send_count]"]',form)?.closest('.form-group')?.querySelector('label');
      if(limitLabel)limitLabel.textContent='本次最多推送篇数';
      if(submit)submit.textContent='立即推送已审核文章';
      var help=document.createElement('p');
      help.className='alert alert-info';
      help.textContent='提交后立即推送。请先选定站点、文章分类和篇数，再到推送记录及官网核对结果。';
      form.prepend(help);
    }
  }
  function applyUserChrome(user){
    if(!user)return;
    var name=user.nickname||user.username||'';
    all('.user-menu .hidden-xs,.user-header p').forEach(function(el){
      if(el.matches('p')){
        var smalls=all('small',el);
        el.childNodes.forEach(function(node){
          if(node.nodeType===3&&node.textContent.trim())node.textContent='\n                                    '+name+'                                    ';
        });
        var quota=quotaLabel(user);
        if(smalls[1])smalls[1].textContent='剩余点数：'+quota.score;
        if(smalls[2])smalls[2].textContent='余额：'+quota.balance;
      }else el.textContent=name;
    });
    if(user.avatar){
      all('.user-menu .user-image,.user-header img').forEach(function(img){img.src=user.avatar;});
    }
  }
  function fillDashboard(){
    if(pageKey!=='dashboard'||!window.GeoAPI)return Promise.resolve();
    return window.GeoAPI.dashboard().then(function(result){
      if(!result.ok||!result.data)return;
      var data=result.data;
      var user=data.user||{};
      var stats=data.stats||{};
      var cards=all('.balance-card .balance-num');
      if(cards[0])cards[0].textContent=unlimitedQuota(user)?'无限':'¥ '+Number(user.balance||0).toFixed(2);
      if(cards[1])cards[1].textContent=unlimitedQuota(user)?'无限':String(Number(user.score||0));
      var foots=all('.balance-card .balance-foot span');
      if(foots[0])foots[0].textContent='本月变动 ¥'+Number(stats.month_money_delta||0).toFixed(2);
      if(foots[1])foots[1].textContent='本月变动 '+Number(stats.month_score_delta||0)+'点';
      var quickBalance=one('.quick-grid .quick b');
      if(quickBalance)quickBalance.textContent=unlimitedQuota(user)?'无限':Number(user.balance||0).toFixed(2)+'元';
      var chart=data.chart||{};
      var series=chart.series||[];
      var max=Math.max.apply(null,series.concat([1]));
      var line=one('#lineChart path,svg#lineChart path,.chart-line path');
      if(line&&series.length){
        var points=series.map(function(value,index){
          var x=(index/(series.length-1||1))*100;
          var y=100-(Number(value)/max)*80-10;
          return x+','+y;
        }).join(' ');
        line.setAttribute('d','M '+points.replace(/ /g,' L '));
      }
      all('.bar-chart .bar, .bars .bar, [data-chart-bar]').forEach(function(bar,index){
        var value=series[index]||0;
        bar.style.height=Math.max(4,Math.round((Number(value)/max)*100))+'%';
        bar.title=String(value);
      });
    }).catch(function(){});
  }
  clarifyWorkflowForms();
  all('button.query-button,button.pingpai_jiexi').forEach(function(button){button.type='button';});
  document.addEventListener('click',function(event){
    var link=event.target.closest('a[data-geo-nav]');
    if(!link||event.defaultPrevented||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;
    event.preventDefault();
    navigate(link.href);
  });
  bindSidebarNavigation();
  fixSidebarScroll();
  window.addEventListener('resize', fixSidebarScroll);
  if(table&&!apiResource()){try{var saved=localStorage.getItem(stateKey);if(saved){table.tBodies[0].innerHTML=saved;refreshRows();}}catch(e){}}
  ensureAuth().then(function(ok){
    if(!ok)return;
    if(window.GeoWorkflow)window.GeoWorkflow.init();
    if(window.GeoAPI){
      window.GeoAPI.me().then(function(result){
        if(!result.ok)return;
        if(shell)applyUserChrome(result.data);
        if(/analyze/.test(pageKey)&&unlimitedQuota(result.data)){
          all('.query-button span').forEach(function(el){
            if(el.querySelector('.real_price'))el.textContent='创建AI诊断任务（无限额度，不扣费）';
          });
        }
      });
    }
    var chain=Promise.resolve();
    if(/-add$|-edit|tougao|settle|configure/.test(pageKey)||new URLSearchParams(location.search).has('editId')){
      chain=chain.then(loadSelectOptions).then(hydrateEditForm);
    }
    if(apiResource()&&!/-add$|-edit|tougao|settle|configure/.test(pageKey))chain=chain.then(loadRemoteRows);
    if(pageKey==='dashboard')chain=chain.then(fillDashboard);
    if(pageKey==='article')chain=chain.then(function(){ensureArticleExport();});
    if(pageKey==='company_keyword')chain=chain.then(ensureKeywordExtractionLink);
    if(pageKey==='visibility')chain=chain.then(loadVisibility);
    if(pageKey==='prompt_test'||pageKey==='knowledge_import')chain=chain.then(loadSelectOptions);
    if(pageKey==='general-profile'&&window.GeoAPI){
      chain=chain.then(function(){return window.GeoAPI.me();}).then(function(result){
        if(!result.ok)return;
        var user=result.data||{};
        var nick=one('#nickname');if(nick)nick.value=user.nickname||user.username||'';
        ensureHiddenInput('c-avatar').value=user.avatar||'';
        if(user.avatar){var img=one('.profile-user-img,.img-circle.thumbnail');if(img)img.src=user.avatar;}
      });
    }
    return chain;
  });
  fetch('/backend-routes.json').then(function(response){if(!response.ok)throw new Error('route map');return response.json();}).then(function(result){
    routes=result.routes||result;
    if(Array.isArray(routes))routes=Object.fromEntries(routes.map(function(r){return [r.path,r.file||'/backend-pages/'+r.key+'.html'];}));
    if(shell){installWorkflowMenu();navigate(decodeURIComponent(location.hash.slice(1))||'/user/geo-workflow');}
    else if(parent===window && new URLSearchParams(location.search).has('ref')){location.replace('/user/index/index/#'+encodeURIComponent(location.pathname.replace(/\/$/,'')));}
  }).catch(function(){message('本地页面目录加载失败，请重新构建');});
  fetch('/backend-interactions.json').then(function(response){return response.ok?response.json():{};}).then(function(value){modalLayouts=value;}).catch(function(){});
}());
