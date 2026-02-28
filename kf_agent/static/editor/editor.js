(function () {
  'use strict';

  const API_BASE = '';
  const STEP_TYPES = [
    { id: 'launch', label: '启动程序' },
    { id: 'wait_window', label: '等待窗口' },
    { id: 'click', label: '点击' },
    { id: 'input_text', label: '输入文本' },
    { id: 'wait', label: '等待' },
    { id: 'hotkey', label: '快捷键' },
    { id: 'close_window', label: '关闭窗口' },
  ];

  function defaultStep(type) {
    switch (type) {
      case 'launch':
        return { type: 'launch', path: '', args: null, cwd: null };
      case 'wait_window':
        return { type: 'wait_window', title: null, class_name: null, timeout_seconds: 30 };
      case 'click':
        return { type: 'click', element: null, x: null, y: null };
      case 'input_text':
        return { type: 'input_text', element: null, text: '', clear_first: true };
      case 'wait':
        return { type: 'wait', seconds: 1 };
      case 'hotkey':
        return { type: 'hotkey', keys: ['ctrl', 'c'] };
      case 'close_window':
        return { type: 'close_window', title: null, class_name: null, kill_process: false };
      default:
        return { type: 'wait', seconds: 1 };
    }
  }

  function stepSummary(step) {
    if (!step || !step.type) return '';
    switch (step.type) {
      case 'launch':
        return step.path || '(未设置路径)';
      case 'wait_window':
        return step.title ? `等待: ${step.title}` : `超时 ${step.timeout_seconds || 30}s`;
      case 'click':
        if (step.element) {
          if (step.element.image) return `图像: ${typeof step.element.image === 'string' ? step.element.image : (step.element.image?.image || '')}`;
          if (step.element.coord) return `坐标: (${step.element.coord.x},${step.element.coord.y})`;
          if (step.element.control) return '控件';
        }
        if (step.x != null && step.y != null) return `(${step.x}, ${step.y})`;
        return '(未设置)';
      case 'input_text':
        return step.text ? `"${step.text.substring(0, 20)}${step.text.length > 20 ? '...' : ''}"` : '(空)';
      case 'wait':
        return `${step.seconds || 0} 秒`;
      case 'hotkey':
        return (step.keys && step.keys.length) ? step.keys.join('+') : '(未设置)';
      case 'close_window':
        return step.title ? `关闭: ${step.title}` : '关闭窗口';
      default:
        return step.type;
    }
  }

  const state = {
    platformList: [],
    config: null,
    selectedStep: null,
    addingToFlow: null,
    filePickerStep: null,
    filePickerPathInput: null,
    filePickerCurrentPath: null,
    resources: {
      controls: [],
      images: [],
    },
  };

  function getEl(id) {
    return document.getElementById(id);
  }

  function showToast(message, isError) {
    const el = getEl('toast');
    el.textContent = message;
    el.className = 'toast ' + (isError ? 'error' : 'success');
    el.classList.remove('hidden');
    setTimeout(function () {
      el.classList.add('hidden');
    }, 3000);
  }

  function requestJson(url, options) {
    return fetch(url, options).then(function (r) {
      if (!r.ok) {
        return r.json()
          .catch(function () { return { detail: r.statusText }; })
          .then(function (d) { throw new Error(d.detail || r.statusText || '请求失败'); });
      }
      return r.json();
    });
  }

  function openLaunchFilePicker(step, pathInput) {
    state.filePickerStep = step;
    state.filePickerPathInput = pathInput;
    state.filePickerCurrentPath = null;
    getEl('filePickerParent').disabled = true;
    getEl('launchFilePickerModal').classList.remove('hidden');
    getEl('filePickerPath').textContent = '根目录';
    getEl('filePickerList').innerHTML = '<div class="file-picker-loading">加载中…</div>';
    loadFilePickerList(null);
  }

  function closeLaunchFilePicker() {
    getEl('launchFilePickerModal').classList.add('hidden');
    state.filePickerStep = null;
    state.filePickerPathInput = null;
    state.filePickerCurrentPath = null;
  }

  function loadFilePickerList(path) {
    const q = path ? '?path=' + encodeURIComponent(path) : '';
    fetch(API_BASE + '/config/list-dir' + q)
      .then(function (r) {
        if (!r.ok) return r.json().then(function (d) { throw new Error(d.detail || r.statusText); });
        return r.json();
      })
      .then(function (data) {
        state.filePickerCurrentPath = path || null;
        getEl('filePickerParent').disabled = !path;
        if (data.roots) {
          getEl('filePickerPath').textContent = '根目录';
          renderFilePickerList(data.roots, true);
        } else {
          getEl('filePickerPath').textContent = data.current || path || '';
          renderFilePickerList(data.entries || [], false);
        }
      })
      .catch(function (e) {
        getEl('filePickerList').innerHTML = '<div class="file-picker-loading file-picker-error">' + escapeHtml(e.message || String(e)) + '</div>';
      });
  }

  function renderFilePickerList(entries, isRoots) {
    const listEl = getEl('filePickerList');
    const step = state.filePickerStep;
    const pathInput = state.filePickerPathInput;
    if (!entries || entries.length === 0) {
      listEl.innerHTML = '<div class="file-picker-loading">（空）</div>';
      return;
    }
    listEl.innerHTML = entries.map(function (entry) {
      const cls = entry.is_dir ? 'folder' : (entry.name.toLowerCase().match(/\.(exe|bat|cmd)$/) ? 'executable' : '');
      return '<div class="file-picker-item ' + cls + '" data-path="' + escapeHtml(entry.path) + '" data-isdir="' + (entry.is_dir ? '1' : '0') + '">' + escapeHtml(entry.name) + '</div>';
    }).join('');
    listEl.querySelectorAll('.file-picker-item').forEach(function (el) {
      el.addEventListener('click', function () {
        const path = el.getAttribute('data-path');
        const isDir = el.getAttribute('data-isdir') === '1';
        if (isDir) {
          loadFilePickerList(path);
        } else {
          if (step) step.path = path;
          if (pathInput) pathInput.value = path;
          updateStepListSummaries();
          showToast('已选择: ' + (path || '').split(/[/\\]/).pop());
          closeLaunchFilePicker();
        }
      });
    });
  }

  function filePickerGoParent() {
    const cur = state.filePickerCurrentPath;
    if (!cur) return;
    var parentPath;
    if (cur.match(/^[A-Za-z]:\\?$/)) {
      parentPath = null;
    } else if (cur === '/' || cur === '') {
      parentPath = null;
    } else {
      var parts = cur.replace(/\\/g, '/').split('/').filter(Boolean);
      if (parts.length <= 1) {
        if (cur.indexOf('\\') >= 0) parentPath = parts[0] + '\\';
        else parentPath = '/';
      } else {
        parts.pop();
        parentPath = cur.indexOf('\\') >= 0 ? parts.join('\\') : '/' + parts.join('/');
      }
    }
    if (parentPath === undefined) parentPath = null;
    loadFilePickerList(parentPath);
  }

  function setPlatformSelectOptions() {
    const sel = getEl('platformSelect');
    sel.innerHTML = '<option value="">-- 选择平台 --</option>';
    state.platformList.forEach(function (item) {
      const opt = document.createElement('option');
      const platformId = typeof item === 'object' ? (item.platform || item.platform_id || '') : item;
      const label = typeof item === 'object' ? (item.display_name || platformId) : platformId;
      opt.value = platformId;
      opt.textContent = label || platformId;
      sel.appendChild(opt);
    });
  }

  function showNewPlatformInputs(show) {
    getEl('btnNewPlatform').classList.toggle('hidden', show);
    getEl('newPlatformId').classList.toggle('hidden', !show);
    getEl('newDisplayName').classList.toggle('hidden', !show);
    getEl('btnConfirmNew').classList.toggle('hidden', !show);
    getEl('btnCancelNew').classList.toggle('hidden', !show);
    getEl('platformSelect').classList.toggle('hidden', show);
    if (!show) {
      getEl('newPlatformId').value = '';
      getEl('newDisplayName').value = '';
    }
  }

  function loadPlatformList() {
    return fetch(API_BASE + '/customer_service/platforms')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        state.platformList = data.platforms || [];
        setPlatformSelectOptions();
      })
      .catch(function (err) {
        showToast('加载平台列表失败: ' + err.message, true);
      });
  }

  function loadConfig(platformId) {
    return requestJson(API_BASE + '/config/platforms/' + encodeURIComponent(platformId))
      .then(function (data) {
        state.config = {
          platform: data.platform || platformId,
          display_name: data.display_name ?? null,
          open: Array.isArray(data.open) ? data.open : [],
          close: Array.isArray(data.close) ? data.close : [],
        };
        state.selectedStep = null;
        render();
        getEl('btnSave').disabled = false;
        getEl('platformDisplayName').textContent = state.config.display_name ? ' - ' + state.config.display_name : '';
        getEl('displayNameInput').value = state.config.display_name || '';
        getEl('displayNameEdit').classList.remove('hidden');
        getEl('btnDeletePlatform').disabled = false;
        return loadResources(platformId);
      })
      .catch(function (err) {
        showToast('加载配置失败: ' + err.message, true);
      });
  }

  function loadResources(platformId) {
    return requestJson(API_BASE + '/config/platforms/' + encodeURIComponent(platformId) + '/resources')
      .then(function (data) {
        state.resources.controls = Array.isArray(data.controls) ? data.controls : [];
        state.resources.images = Array.isArray(data.images) ? data.images : [];
        render();
      })
      .catch(function (err) {
        state.resources.controls = [];
        state.resources.images = [];
        render();
        showToast('加载资源库失败: ' + err.message, true);
      });
  }

  function renderStepList(flowKey, containerId) {
    const list = state.config && state.config[flowKey] ? state.config[flowKey] : [];
    const container = getEl(containerId);
    container.innerHTML = '';
    list.forEach(function (step, index) {
      const div = document.createElement('div');
      div.className = 'step-item' + (state.selectedStep && state.selectedStep.flow === flowKey && state.selectedStep.index === index ? ' selected' : '');
      div.setAttribute('data-flow', flowKey);
      div.setAttribute('data-index', String(index));
      div.innerHTML =
        '<span class="step-index">' + (index + 1) + '</span>' +
        '<span class="step-type">' + (step.type || '') + '</span>' +
        '<span class="step-summary">' + escapeHtml(stepSummary(step)) + '</span>' +
        '<div class="step-actions">' +
        '<button type="button" data-action="up" title="上移">↑</button>' +
        '<button type="button" data-action="down" title="下移">↓</button>' +
        '<button type="button" data-action="edit" title="编辑">编辑</button>' +
        '<button type="button" data-action="delete" title="删除">删除</button>' +
        '</div>';
      container.appendChild(div);
    });
  }

  function escapeHtml(s) {
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  }

  function render() {
    if (!state.config) {
      getEl('openStepList').innerHTML = '';
      getEl('closeStepList').innerHTML = '';
      getEl('stepEditorPanel').classList.add('empty');
      getEl('stepEditorContent').innerHTML = '<p>请选择或新建平台</p>';
      renderResourcePanel();
      return;
    }
    getEl('stepEditorPanel').classList.remove('empty');
    renderStepList('open', 'openStepList');
    renderStepList('close', 'closeStepList');
    if (state.selectedStep) {
      renderStepEditor(state.selectedStep.flow, state.selectedStep.index);
    } else {
      getEl('stepEditorContent').innerHTML = '<p>点击步骤「编辑」或添加新步骤</p>';
    }
    renderResourcePanel();
  }

  function renderResourcePanel() {
    const hint = getEl('resourcePanelHint');
    const content = getEl('resourcePanelContent');
    if (!state.config) {
      hint.textContent = '请选择平台后管理资源。';
      content.classList.add('hidden');
      getEl('resourceControlList').innerHTML = '';
      getEl('resourceImageList').innerHTML = '';
      return;
    }
    hint.textContent = '当前平台：' + state.config.platform;
    content.classList.remove('hidden');
    renderResourceList('controls');
    renderResourceList('images');
  }

  function renderResourceList(type) {
    const listEl = getEl(type === 'controls' ? 'resourceControlList' : 'resourceImageList');
    const list = type === 'controls' ? state.resources.controls : state.resources.images;
    if (!list.length) {
      listEl.innerHTML = '<div class="resource-item"><div class="resource-item-sub">暂无资源</div></div>';
      return;
    }
    listEl.innerHTML = list.map(function (item) {
      var sub = '';
      if (type === 'controls') {
        var c = item.payload || {};
        sub = [c.window_title, c.control_type, c.name].filter(Boolean).join(' / ') || '控件信息';
      } else {
        var img = item.payload || {};
        sub = (img.image || '图片') + '，阈值 ' + (img.threshold != null ? img.threshold : 0.8);
      }
      return (
        '<div class="resource-item" data-res-type="' + type + '" data-res-id="' + escapeHtml(item.id) + '">' +
        '<div class="resource-item-title">' + escapeHtml(item.name || item.id) + '</div>' +
        '<div class="resource-item-sub">' + escapeHtml(sub) + '</div>' +
        '<div class="resource-item-actions">' +
        '<button type="button" data-action="resource-use">用于当前步骤</button>' +
        '<button type="button" data-action="resource-locate">定位</button>' +
        '<button type="button" data-action="resource-rename">重命名</button>' +
        '<button type="button" data-action="resource-delete">删除</button>' +
        '</div>' +
        '</div>'
      );
    }).join('');
  }

  function getStep(flow, index) {
    if (!state.config || !state.config[flow]) return null;
    return state.config[flow][index] || null;
  }

  function renderStepEditor(flow, index) {
    const step = getStep(flow, index);
    if (!step) {
      getEl('stepEditorContent').innerHTML = '<p>步骤不存在</p>';
      return;
    }
    const type = step.type || 'wait';
    let html = '<div class="form-group"><label>类型</label><span>' + type + '</span></div>';
    if (type === 'launch') {
      html +=
        '<div class="form-group"><label>路径 (path)</label>' +
        '<p class="field-hint">可填写服务器本机路径（如 C:\\Program Files (x86)\\AliWorkbench\\千牛.exe），或点击「选择服务器文件」从服务器磁盘中选取。</p>' +
        '<div class="path-row"><input type="text" data-field="path" value="' + escapeHtml(step.path || '') + '" placeholder="可执行文件完整路径" />' +
        '<button type="button" class="btn-choose-file" data-action="launch-choose-file">选择服务器文件</button></div></div>' +
        '<div class="form-group"><label>参数 args (逗号分隔)</label><input type="text" data-field="args" value="' + escapeHtml(Array.isArray(step.args) ? step.args.join(', ') : '') + '" placeholder="可选" /></div>' +
        '<div class="form-group"><label>工作目录 (cwd)</label><input type="text" data-field="cwd" value="' + escapeHtml(step.cwd || '') + '" placeholder="建议与 path 所在目录一致，如 C:\\Program Files (x86)\\AliWorkbench" /></div>';
    } else if (type === 'wait_window') {
      html +=
        '<div class="form-group"><label>窗口标题 (title)</label><input type="text" data-field="title" value="' + escapeHtml(step.title || '') + '" /></div>' +
        '<div class="form-group"><label>类名 (class_name)</label><input type="text" data-field="class_name" value="' + escapeHtml(step.class_name || '') + '" /></div>' +
        '<div class="form-group"><label>超时秒数 (timeout_seconds)</label><input type="number" data-field="timeout_seconds" step="any" value="' + (step.timeout_seconds ?? 30) + '" /></div>';
    } else if (type === 'click') {
      html += renderElementEditor(step.element, 'click');
      html += '<div class="form-group"><label>或直接坐标 x</label><input type="number" data-field="x" value="' + (step.x ?? '') + '" placeholder="可选" /></div>';
      html += '<div class="form-group"><label>y</label><input type="number" data-field="y" value="' + (step.y ?? '') + '" placeholder="可选" /></div>';
    } else if (type === 'input_text') {
      html += renderElementEditor(step.element, 'input_text');
      html +=
        '<div class="form-group"><label>文本 (text)</label><textarea data-field="text" rows="2">' + escapeHtml(step.text || '') + '</textarea></div>' +
        '<div class="form-group"><label><input type="checkbox" data-field="clear_first" ' + (step.clear_first !== false ? 'checked' : '') + ' /> 先清空</label></div>';
    } else if (type === 'wait') {
      html += '<div class="form-group"><label>秒数 (seconds)</label><input type="number" data-field="seconds" step="any" value="' + (step.seconds ?? 1) + '" /></div>';
    } else if (type === 'hotkey') {
      const keys = Array.isArray(step.keys) ? step.keys.join(', ') : '';
      html += '<div class="form-group"><label>按键 (keys, 逗号分隔)</label><input type="text" data-field="keys" value="' + escapeHtml(keys) + '" placeholder="ctrl, c" /></div>';
    } else if (type === 'close_window') {
      html +=
        '<div class="form-group"><label>窗口标题 (title)</label><input type="text" data-field="title" value="' + escapeHtml(step.title || '') + '" /></div>' +
        '<div class="form-group"><label>类名 (class_name)</label><input type="text" data-field="class_name" value="' + escapeHtml(step.class_name || '') + '" /></div>' +
        '<div class="form-group"><label><input type="checkbox" data-field="kill_process" ' + (step.kill_process ? 'checked' : '') + ' /> 结束进程</label></div>';
    }
    getEl('stepEditorContent').innerHTML = html;
    bindStepEditorInputs(flow, index);
  }

  function renderElementEditor(element, stepType) {
    const el = element || {};
    const hasCoord = el.coord != null;
    const hasImage = el.image != null;
    const hasControl = el.control != null;
    const imgVal = typeof el.image === 'string' ? el.image : (el.image && el.image.image) || '';
    const thresh = (el.image && typeof el.image === 'object' && el.image.threshold != null) ? el.image.threshold : 0.8;
    const c = el.control || {};
    const coord = el.coord || {};
    const controlOptions = state.resources.controls.map(function (item) {
      return '<option value="' + escapeHtml(item.id) + '">' + escapeHtml(item.name || item.id) + '</option>';
    }).join('');
    const imageOptions = state.resources.images.map(function (item) {
      return '<option value="' + escapeHtml(item.id) + '">' + escapeHtml(item.name || item.id) + '</option>';
    }).join('');
    return (
      '<div class="form-group element-editor" data-step-type="' + stepType + '">' +
      '<label>元素定位</label>' +
      '<div class="element-tabs">' +
      '<button type="button" data-elem-tab="coord" class="' + (hasCoord ? 'active' : '') + '">坐标</button>' +
      '<button type="button" data-elem-tab="image" class="' + (hasImage ? 'active' : '') + '">图像</button>' +
      '<button type="button" data-elem-tab="control" class="' + (hasControl ? 'active' : '') + '">控件</button>' +
      '</div>' +
      '<div class="element-panel" data-panel="coord" style="' + (hasCoord ? '' : 'display:none') + '">' +
      '<div class="form-row"><label>x</label><input type="number" data-elem="coord.x" value="' + (coord.x ?? '') + '" /></div>' +
      '<div class="form-row"><label>y</label><input type="number" data-elem="coord.y" value="' + (coord.y ?? '') + '" /></div>' +
      '<div class="form-row"><label>relative_to</label><input type="text" data-elem="coord.relative_to" value="' + escapeHtml(coord.relative_to || 'screen') + '" placeholder="screen / window" /></div>' +
      '<div class="form-row"><label>window_title</label><input type="text" data-elem="coord.window_title" value="' + escapeHtml(coord.window_title || '') + '" /></div>' +
      '</div>' +
      '<div class="element-panel" data-panel="image" style="' + (hasImage ? '' : 'display:none') + '">' +
      '<div class="resource-select-row"><select data-resource-select="image"><option value="">从资源库选择图片...</option>' + imageOptions + '</select><button type="button" data-action="apply-image-resource">使用</button></div>' +
      '<div class="form-row"><label>image</label><input type="text" data-elem="image.image" value="' + escapeHtml(imgVal) + '" placeholder="文件名或路径" /></div>' +
      '<div class="form-row"><label>threshold</label><input type="number" data-elem="image.threshold" step="0.01" value="' + thresh + '" /></div>' +
      '<div class="form-row"><button type="button" class="btn-pick-image" data-action="image-choose-file">选择图片文件</button><input type="file" class="hidden image-file-input" accept="image/*" data-action="image-file-input" /></div>' +
      '<div class="form-row"><button type="button" class="btn-capture-window" data-action="image-capture-window">从当前窗口截取</button></div>' +
      '<p class="form-hint">点击后本窗口会最小化，请切换到目标窗口后按 <strong>Ctrl+Shift+R</strong> 开始框选，再按住 <strong>Ctrl</strong> 拖动鼠标框选区域，松开即保存；Esc 取消（仅 Windows）</p>' +
      (imgVal ? '<div class="form-row image-preview"><img src="' + (imgVal.indexOf("/") >= 0 ? imgVal : (API_BASE + "/config/templates/" + encodeURIComponent(imgVal))) + '" alt="预览" onerror="this.style.display=\'none\'" /></div>' : '') +
      '</div>' +
      '<div class="element-panel" data-panel="control" style="' + (hasControl ? '' : 'display:none') + '">' +
      '<div class="resource-select-row"><select data-resource-select="control"><option value="">从资源库选择控件...</option>' + controlOptions + '</select><button type="button" data-action="apply-control-resource">使用</button></div>' +
      '<div class="form-row"><button type="button" class="btn-pick-control" data-action="pick-control">开始捕获</button></div>' +
      '<p class="form-hint">点击后请最小化本窗口，将鼠标移到目标控件上会显示红框，按 <strong>Ctrl+Shift+C</strong> 捕获（仅 Windows）</p>' +
      '<div class="form-row"><label>window_title</label><input type="text" data-elem="control.window_title" value="' + escapeHtml(c.window_title || '') + '" /></div>' +
      '<div class="form-row"><label>window_class</label><input type="text" data-elem="control.window_class" value="' + escapeHtml(c.window_class || '') + '" /></div>' +
      '<div class="form-row"><label>control_id</label><input type="number" data-elem="control.control_id" value="' + (c.control_id ?? '') + '" /></div>' +
      '<div class="form-row"><label>automation_id</label><input type="text" data-elem="control.automation_id" value="' + escapeHtml(c.automation_id || '') + '" /></div>' +
      '<div class="form-row"><label>control_type</label><input type="text" data-elem="control.control_type" value="' + escapeHtml(c.control_type || '') + '" /></div>' +
      '<div class="form-row"><label>name</label><input type="text" data-elem="control.name" value="' + escapeHtml(c.name || '') + '" /></div>' +
      '</div>' +
      '</div>'
    );
  }

  function bindStepEditorInputs(flow, index) {
    const step = getStep(flow, index);
    if (!step) return;
    const content = getEl('stepEditorContent');
    content.querySelectorAll('input, textarea').forEach(function (input) {
      const field = input.getAttribute('data-field');
      const elem = input.getAttribute('data-elem');
      function apply() {
        if (field) {
          if (field === 'args') {
            const v = input.value.trim();
            step.args = v ? v.split(',').map(function (s) { return s.trim(); }) : null;
          } else if (field === 'keys') {
            const v = input.value.trim();
            step.keys = v ? v.split(',').map(function (s) { return s.trim(); }) : [];
          } else if (field === 'clear_first' || field === 'kill_process') {
            step[field] = input.checked;
          } else if (input.type === 'number') {
            const n = parseFloat(input.value);
            step[field] = isNaN(n) ? (field === 'timeout_seconds' ? 30 : field === 'seconds' ? 1 : 0) : n;
          } else {
            step[field] = input.value || null;
          }
        } else if (elem) {
          const parts = elem.split('.');
          const root = parts[0];
          const key = parts[1];
          if (!step.element) step.element = {};
          if (root === 'coord') {
            if (!step.element.coord) step.element.coord = {};
            if (key === 'x' || key === 'y') step.element.coord[key] = input.value === '' ? undefined : parseInt(input.value, 10);
            else step.element.coord[key] = input.value || undefined;
          } else if (root === 'image') {
            if (!step.element.image) step.element.image = { image: '', threshold: 0.8 };
            if (key === 'image') step.element.image.image = input.value || '';
            else if (key === 'threshold') step.element.image.threshold = parseFloat(input.value) || 0.8;
          } else if (root === 'control') {
            if (!step.element.control) step.element.control = {};
            if (key === 'control_id') step.element.control.control_id = input.value === '' ? undefined : parseInt(input.value, 10);
            else step.element.control[key] = input.value || undefined;
          }
        }
        updateStepListSummaries();
      }
      input.addEventListener('input', apply);
      input.addEventListener('change', apply);
    });
    content.querySelectorAll('.element-tabs button').forEach(function (btn) {
      btn.addEventListener('click', function () {
        const tab = btn.getAttribute('data-elem-tab');
        content.querySelectorAll('.element-tabs button').forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
        content.querySelectorAll('.element-panel').forEach(function (panel) {
          panel.style.display = panel.getAttribute('data-panel') === tab ? '' : 'none';
        });
        if (!step.element) step.element = {};
        if (tab === 'coord') {
          step.element.coord = step.element.coord || { x: 0, y: 0, relative_to: 'screen' };
          step.element.image = null;
          step.element.control = null;
        } else if (tab === 'image') {
          step.element.image = step.element.image || { image: '', threshold: 0.8 };
          step.element.coord = null;
          step.element.control = null;
        } else {
          step.element.control = step.element.control || {};
          step.element.coord = null;
          step.element.image = null;
        }
        render();
      });
    });

    var pathInput = content.querySelector('input[data-field="path"]');
    var launchBtn = content.querySelector('[data-action="launch-choose-file"]');
    if (launchBtn && pathInput) {
      launchBtn.addEventListener('click', function () {
        openLaunchFilePicker(step, pathInput);
      });
    }

    var pickControlBtn = content.querySelector('[data-action="pick-control"]');
    if (pickControlBtn) {
      pickControlBtn.addEventListener('click', function () {
        var btn = this;
        var origText = btn.textContent;
        btn.disabled = true;
        btn.textContent = '捕获中…';
        showToast('请最小化本窗口，将鼠标移到目标控件上，按 Ctrl+Shift+C 捕获');
        if (typeof window.minimize === 'function') window.minimize();
        else if (window.blur) window.blur();
        fetch(API_BASE + '/config/pick-control/capture', { method: 'POST' })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (d) { throw new Error(d.detail || r.statusText); });
            return r.json();
          })
          .then(function (data) {
            btn.textContent = origText;
            btn.disabled = false;
            if (data && data.captured === false) {
              showToast(data.detail === 'timeout_or_no_control' ? '未捕获到控件（超时或未按 Ctrl+Shift+C）' : '未捕获到控件', true);
              return;
            }
            if (!step.element) step.element = {};
            step.element.control = {
              window_title: data.window_title || null,
              window_class: data.window_class || null,
              control_id: data.control_id !== undefined && data.control_id !== null ? data.control_id : undefined,
              automation_id: data.automation_id || null,
              control_type: data.control_type || null,
              name: data.name || null,
            };
            step.element.coord = null;
            step.element.image = null;
            render();
            showToast('控件已捕获');
          })
          .catch(function (e) {
            btn.textContent = origText;
            btn.disabled = false;
            showToast(e.message || '捕获失败（仅 Windows 支持）', true);
          });
      });
    }

    var applyControlResourceBtn = content.querySelector('[data-action="apply-control-resource"]');
    if (applyControlResourceBtn) {
      applyControlResourceBtn.addEventListener('click', function () {
        var select = content.querySelector('select[data-resource-select="control"]');
        if (!select || !select.value) {
          showToast('请先选择控件资源', true);
          return;
        }
        var res = state.resources.controls.find(function (x) { return x.id === select.value; });
        if (!res) {
          showToast('控件资源不存在', true);
          return;
        }
        if (!step.element) step.element = {};
        step.element.control = Object.assign({}, res.payload || {});
        step.element.coord = null;
        step.element.image = null;
        render();
        showToast('已应用控件资源: ' + (res.name || res.id));
      });
    }

    var imageChooseBtn = content.querySelector('[data-action="image-choose-file"]');
    var imageFileInput = content.querySelector('.image-file-input');
    if (imageChooseBtn && imageFileInput) {
      imageChooseBtn.addEventListener('click', function () { imageFileInput.click(); });
      imageFileInput.addEventListener('change', function () {
        if (!imageFileInput.files || !imageFileInput.files[0]) return;
        var fd = new FormData();
        fd.append('file', imageFileInput.files[0]);
        fetch(API_BASE + '/config/upload-template', { method: 'POST', body: fd })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            if (!step.element) step.element = {};
            if (!step.element.image) step.element.image = { image: '', threshold: 0.8 };
            step.element.image.image = data.filename;
            step.element.coord = null;
            step.element.control = null;
            render();
            showToast('已选择: ' + data.filename);
          })
          .catch(function (e) { showToast('上传失败: ' + (e.message || String(e)), true); });
        imageFileInput.value = '';
      });
    }

    var captureBtn = content.querySelector('[data-action="image-capture-window"]');
    if (captureBtn) {
      captureBtn.addEventListener('click', function () {
        var btn = this;
        var origText = btn.textContent;
        btn.disabled = true;
        btn.textContent = '截取中…';
        showToast('本窗口将最小化，请切换到目标窗口后按 Ctrl+Shift+R 开始框选');
        if (typeof window.minimize === 'function') window.minimize();
        else if (window.blur) window.blur();
        fetch(API_BASE + '/config/capture-region', { method: 'POST' })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (d) { throw new Error(d.detail || r.statusText); });
            return r.json();
          })
          .then(function (data) {
            btn.textContent = origText;
            btn.disabled = false;
            if (!step.element) step.element = {};
            if (!step.element.image) step.element.image = { image: '', threshold: 0.8 };
            step.element.image.image = data.filename;
            step.element.coord = null;
            step.element.control = null;
            render();
            showToast('已截取: ' + data.filename);
          })
          .catch(function (e) {
            btn.textContent = origText;
            btn.disabled = false;
            showToast(e.message || '截取失败（仅 Windows 支持）', true);
          });
      });
    }

    var applyImageResourceBtn = content.querySelector('[data-action="apply-image-resource"]');
    if (applyImageResourceBtn) {
      applyImageResourceBtn.addEventListener('click', function () {
        var select = content.querySelector('select[data-resource-select="image"]');
        if (!select || !select.value) {
          showToast('请先选择图片资源', true);
          return;
        }
        var res = state.resources.images.find(function (x) { return x.id === select.value; });
        if (!res) {
          showToast('图片资源不存在', true);
          return;
        }
        if (!step.element) step.element = {};
        step.element.image = Object.assign({ threshold: 0.8 }, res.payload || {});
        step.element.coord = null;
        step.element.control = null;
        render();
        showToast('已应用图片资源: ' + (res.name || res.id));
      });
    }
  }

  function applyResourceToCurrentStep(type, resource) {
    if (!state.selectedStep) {
      showToast('请先选择一个 click 或 input_text 步骤', true);
      return;
    }
    var step = getStep(state.selectedStep.flow, state.selectedStep.index);
    if (!step || (step.type !== 'click' && step.type !== 'input_text')) {
      showToast('当前步骤不支持元素资源', true);
      return;
    }
    if (!step.element) step.element = {};
    if (type === 'controls') {
      step.element.control = Object.assign({}, resource.payload || {});
      step.element.coord = null;
      step.element.image = null;
    } else {
      step.element.image = Object.assign({ threshold: 0.8 }, resource.payload || {});
      step.element.coord = null;
      step.element.control = null;
    }
    render();
    showToast('已应用到当前步骤');
  }

  function createControlResourceByCapture() {
    if (!state.config) return;
    showToast('请最小化本窗口，将鼠标移到目标控件上，按 Ctrl+Shift+C 捕获');
    if (typeof window.minimize === 'function') window.minimize();
    else if (window.blur) window.blur();
    requestJson(API_BASE + '/config/pick-control/capture', { method: 'POST' })
      .then(function (data) {
        if (data && data.captured === false) {
          throw new Error('未捕获到控件（超时或未按 Ctrl+Shift+C）');
        }
        var name = prompt('请输入控件资源名称', (data.name || data.control_type || '控件资源').trim());
        if (!name) {
          showToast('已取消新增控件资源');
          return null;
        }
        return requestJson(API_BASE + '/config/platforms/' + encodeURIComponent(state.config.platform) + '/resources/controls', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: name.trim(),
            payload: {
              window_title: data.window_title || null,
              window_class: data.window_class || null,
              control_id: data.control_id !== undefined && data.control_id !== null ? data.control_id : undefined,
              automation_id: data.automation_id || null,
              control_type: data.control_type || null,
              name: data.name || null,
            },
          }),
        });
      })
      .then(function (created) {
        if (!created) return;
        return loadResources(state.config.platform).then(function () {
          showToast('控件资源已新增: ' + (created.name || created.id));
        });
      })
      .catch(function (err) {
        showToast(err.message || '新增控件资源失败', true);
      });
  }

  function createImageResourceFromFilename(filename) {
    if (!state.config || !filename) return Promise.resolve();
    var name = prompt('请输入图片资源名称', filename);
    if (!name) {
      showToast('已取消新增图片资源');
      return Promise.resolve();
    }
    return requestJson(API_BASE + '/config/platforms/' + encodeURIComponent(state.config.platform) + '/resources/images', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name.trim(),
        payload: { image: filename, threshold: 0.8 },
      }),
    }).then(function (created) {
      return loadResources(state.config.platform).then(function () {
        showToast('图片资源已新增: ' + (created.name || created.id));
      });
    });
  }

  function locateResource(type, id) {
    if (!state.config) return;
    requestJson(API_BASE + '/config/platforms/' + encodeURIComponent(state.config.platform) + '/resources/locate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type: type === 'controls' ? 'control' : 'image',
        resource_id: id,
      }),
    }).then(function () {
      showToast('已定位并高亮');
    }).catch(function (err) {
      showToast(err.message || '定位失败', true);
    });
  }

  function renameResource(type, id) {
    if (!state.config) return;
    var list = type === 'controls' ? state.resources.controls : state.resources.images;
    var item = list.find(function (x) { return x.id === id; });
    if (!item) return;
    var name = prompt('请输入新名称', item.name || '');
    if (!name) return;
    requestJson(
      API_BASE + '/config/platforms/' + encodeURIComponent(state.config.platform) + '/resources/' + type + '/' + encodeURIComponent(id) + '/name',
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim() }),
      }
    ).then(function () {
      return loadResources(state.config.platform);
    }).then(function () {
      showToast('重命名成功');
    }).catch(function (err) {
      showToast(err.message || '重命名失败', true);
    });
  }

  function deleteResource(type, id) {
    if (!state.config) return;
    if (!confirm('确认删除该资源吗？')) return;
    requestJson(
      API_BASE + '/config/platforms/' + encodeURIComponent(state.config.platform) + '/resources/' + type + '/' + encodeURIComponent(id),
      { method: 'DELETE' }
    ).then(function () {
      return loadResources(state.config.platform);
    }).then(function () {
      showToast('删除成功');
    }).catch(function (err) {
      showToast(err.message || '删除失败', true);
    });
  }

  function updateStepListSummaries() {
    if (!state.config) return;
    ['open', 'close'].forEach(function (flow) {
      const list = state.config[flow];
      const container = getEl(flow === 'open' ? 'openStepList' : 'closeStepList');
      container.querySelectorAll('.step-item').forEach(function (item, i) {
        const summaryEl = item.querySelector('.step-summary');
        if (summaryEl && list[i]) summaryEl.textContent = stepSummary(list[i]);
      });
    });
  }

  function moveStep(flow, index, dir) {
    if (!state.config || !state.config[flow]) return;
    const arr = state.config[flow];
    const next = index + dir;
    if (next < 0 || next >= arr.length) return;
    const t = arr[index];
    arr[index] = arr[next];
    arr[next] = t;
    state.selectedStep = { flow: flow, index: next };
    render();
  }

  function deleteStep(flow, index) {
    if (!state.config || !state.config[flow]) return;
    state.config[flow].splice(index, 1);
    state.selectedStep = null;
    render();
  }

  function addStep(flow, type) {
    if (!state.config) return;
    const step = defaultStep(type);
    state.config[flow].push(step);
    state.selectedStep = { flow: flow, index: state.config[flow].length - 1 };
    getEl('stepTypeModal').classList.add('hidden');
    state.addingToFlow = null;
    render();
  }

  function deletePlatform() {
    if (!state.config) return;
    const platformId = state.config.platform;
    if (!confirm('确定要删除平台「' + platformId + '」吗？此操作将删除该平台的配置文件，且不可恢复。')) return;
    fetch(API_BASE + '/config/platforms/' + encodeURIComponent(platformId), { method: 'DELETE' })
      .then(function (r) {
        if (!r.ok) return r.json().then(function (d) { throw new Error(d.detail || '删除失败'); });
        return r.json();
      })
      .then(function () {
        showToast('已删除平台: ' + platformId);
        state.config = null;
        state.selectedStep = null;
        getEl('btnSave').disabled = true;
        getEl('btnDeletePlatform').disabled = true;
        getEl('platformDisplayName').textContent = '';
        getEl('displayNameEdit').classList.add('hidden');
        loadPlatformList().then(function () {
          getEl('platformSelect').value = '';
          render();
        });
      })
      .catch(function (err) {
        showToast('删除失败: ' + (err.message || String(err)), true);
      });
  }

  function saveConfig() {
    if (!state.config) return;
    const platformId = state.config.platform;
    const body = {
      open: state.config.open,
      close: state.config.close,
      display_name: state.config.display_name || null,
    };
    fetch(API_BASE + '/config/platforms/' + encodeURIComponent(platformId), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then(function (r) {
        if (!r.ok) return r.json().then(function (d) { throw new Error(d.detail || '保存失败'); });
        return r.json();
      })
      .then(function () {
        showToast('保存成功');
        if (state.platformList.indexOf(platformId) === -1) {
          state.platformList.push(platformId);
          state.platformList.sort();
          setPlatformSelectOptions();
          getEl('platformSelect').value = platformId;
        }
      })
      .catch(function (err) {
        showToast('保存失败: ' + (err.message || String(err)), true);
      });
  }

  function init() {
    loadPlatformList();

    getEl('platformSelect').addEventListener('change', function () {
      const id = this.value;
      if (!id) {
        state.config = null;
        state.selectedStep = null;
        state.resources = { controls: [], images: [] };
        render();
        getEl('btnSave').disabled = true;
        getEl('btnDeletePlatform').disabled = true;
        getEl('platformDisplayName').textContent = '';
        getEl('displayNameEdit').classList.add('hidden');
        return;
      }
      loadConfig(id);
    });

    getEl('btnNewPlatform').addEventListener('click', function () {
      showNewPlatformInputs(true);
    });

    getEl('btnCancelNew').addEventListener('click', function () {
      showNewPlatformInputs(false);
    });

    getEl('btnConfirmNew').addEventListener('click', function () {
      const id = getEl('newPlatformId').value.trim();
      const name = getEl('newDisplayName').value.trim();
      if (!id) {
        showToast('请输入平台 ID', true);
        return;
      }
      state.config = {
        platform: id,
        display_name: name || null,
        open: [],
        close: [],
      };
      state.selectedStep = null;
      state.resources = { controls: [], images: [] };
      showNewPlatformInputs(false);
      setPlatformSelectOptions();
      var opt = document.createElement('option');
      opt.value = id;
      opt.textContent = id;
      getEl('platformSelect').appendChild(opt);
      getEl('platformSelect').value = id;
      getEl('btnSave').disabled = false;
      getEl('platformDisplayName').textContent = name ? ' - ' + name : '';
      getEl('displayNameInput').value = name || '';
      getEl('displayNameEdit').classList.remove('hidden');
      getEl('btnDeletePlatform').disabled = false;
      render();
      loadResources(id);
      showToast('已创建新平台配置，请添加步骤后保存');
    });

    getEl('displayNameInput').addEventListener('input', function () {
      if (state.config) state.config.display_name = this.value || null;
    });
    getEl('displayNameInput').addEventListener('change', function () {
      if (state.config) state.config.display_name = this.value || null;
      getEl('platformDisplayName').textContent = state.config && state.config.display_name ? ' - ' + state.config.display_name : '';
    });

    getEl('btnSave').addEventListener('click', saveConfig);

    getEl('btnDeletePlatform').addEventListener('click', deletePlatform);

    getEl('btnAddOpen').addEventListener('click', function () {
      state.addingToFlow = 'open';
      getEl('stepTypeGrid').innerHTML = STEP_TYPES.map(function (t) {
        return '<button type="button" data-type="' + t.id + '">' + escapeHtml(t.label) + ' (' + t.id + ')</button>';
      }).join('');
      getEl('stepTypeGrid').querySelectorAll('button').forEach(function (btn) {
        btn.addEventListener('click', function () {
          addStep('open', btn.getAttribute('data-type'));
        });
      });
      getEl('stepTypeModal').classList.remove('hidden');
    });

    getEl('btnAddClose').addEventListener('click', function () {
      state.addingToFlow = 'close';
      getEl('stepTypeGrid').innerHTML = STEP_TYPES.map(function (t) {
        return '<button type="button" data-type="' + t.id + '">' + escapeHtml(t.label) + ' (' + t.id + ')</button>';
      }).join('');
      getEl('stepTypeGrid').querySelectorAll('button').forEach(function (btn) {
        btn.addEventListener('click', function () {
          addStep('close', btn.getAttribute('data-type'));
        });
      });
      getEl('stepTypeModal').classList.remove('hidden');
    });

    getEl('btnCloseTypeModal').addEventListener('click', function () {
      getEl('stepTypeModal').classList.add('hidden');
      state.addingToFlow = null;
    });

    getEl('btnCloseLaunchFilePicker').addEventListener('click', closeLaunchFilePicker);
    getEl('filePickerParent').addEventListener('click', function () {
      if (!this.disabled) filePickerGoParent();
    });

    getEl('openStepList').addEventListener('click', delegateStepList);
    getEl('closeStepList').addEventListener('click', delegateStepList);
    getEl('btnAddControlResource').addEventListener('click', createControlResourceByCapture);
    getEl('btnUploadImageResource').addEventListener('click', function () {
      if (!state.config) return;
      getEl('resourceImageFileInput').click();
    });
    getEl('resourceImageFileInput').addEventListener('change', function () {
      var input = getEl('resourceImageFileInput');
      if (!input.files || !input.files[0] || !state.config) return;
      var fd = new FormData();
      fd.append('file', input.files[0]);
      requestJson(API_BASE + '/config/upload-template', { method: 'POST', body: fd })
        .then(function (data) { return createImageResourceFromFilename(data.filename); })
        .catch(function (err) { showToast(err.message || '上传图片失败', true); })
        .finally(function () { input.value = ''; });
    });
    getEl('btnCaptureImageResource').addEventListener('click', function () {
      if (!state.config) return;
      showToast('本窗口将最小化，请切换到目标窗口后按 Ctrl+Shift+R 开始框选');
      if (typeof window.minimize === 'function') window.minimize();
      else if (window.blur) window.blur();
      requestJson(API_BASE + '/config/capture-region', { method: 'POST' })
        .then(function (data) { return createImageResourceFromFilename(data.filename); })
        .catch(function (err) { showToast(err.message || '截取失败', true); });
    });
    getEl('resourcePanelContent').addEventListener('click', function (e) {
      var itemEl = e.target.closest('.resource-item');
      var btn = e.target.closest('button');
      if (!itemEl || !btn || !state.config) return;
      var type = itemEl.getAttribute('data-res-type');
      var id = itemEl.getAttribute('data-res-id');
      var action = btn.getAttribute('data-action');
      var list = type === 'controls' ? state.resources.controls : state.resources.images;
      var resource = list.find(function (x) { return x.id === id; });
      if (!resource) {
        showToast('资源不存在', true);
        return;
      }
      if (action === 'resource-use') applyResourceToCurrentStep(type, resource);
      else if (action === 'resource-locate') locateResource(type, id);
      else if (action === 'resource-rename') renameResource(type, id);
      else if (action === 'resource-delete') deleteResource(type, id);
    });

    function delegateStepList(e) {
      const item = e.target.closest('.step-item');
      const btn = e.target.closest('.step-actions button');
      if (!state.config) return;
      if (item) {
        const flow = item.getAttribute('data-flow');
        const index = parseInt(item.getAttribute('data-index'), 10);
        if (btn) {
          const action = btn.getAttribute('data-action');
          if (action === 'up') moveStep(flow, index, -1);
          else if (action === 'down') moveStep(flow, index, 1);
          else if (action === 'edit') {
            state.selectedStep = { flow: flow, index: index };
            render();
          } else if (action === 'delete') deleteStep(flow, index);
        } else {
          state.selectedStep = { flow: flow, index: index };
          render();
        }
      }
    }

    render();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
