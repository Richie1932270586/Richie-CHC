(() => {
  const CONTENT_DATA_URL = (window.PORTFOLIO_CONTENT_URL || 'data/site-content.json').trim();
  const EDITOR_API_BASE = (window.PORTFOLIO_EDITOR_API_BASE || '').trim().replace(/\/$/, '');
  const ADMIN_TOKEN_KEY = 'portfolio-admin-token';
  const DEFAULT_PROJECT_FOLDER_SUMMARY = '可选：选择包含 <code>index.html</code> 的项目目录；如果只想放直达链接，也可以直接填写链接。';
  const DEFAULT_DELETE_ENTRY_MESSAGE = '确认后，这项内容会从当前页面移除。';

  const items = document.querySelectorAll('.reveal');
  const io = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        io.unobserve(entry.target);
      }
    });
  }, { threshold: 0.08 });
  items.forEach((item) => io.observe(item));

  const adminToggleButton = document.getElementById('adminToggleButton');
  const projectGrid = document.getElementById('projectGrid');
  const experienceTimeline = document.getElementById('experienceTimeline');
  const projectModal = document.getElementById('projectModal');
  const experienceModal = document.getElementById('experienceModal');
  const deleteEntryModal = document.getElementById('deleteEntryModal');
  const adminAuthModal = document.getElementById('adminAuthModal');
  const projectForm = document.getElementById('projectForm');
  const experienceForm = document.getElementById('experienceForm');
  const adminAuthForm = document.getElementById('adminAuthForm');
  const openProjectModalBtn = document.getElementById('openProjectModal');
  const openExperienceModalBtn = document.getElementById('openExperienceModal');
  const closeProjectModalBtn = document.getElementById('closeProjectModal');
  const closeExperienceModalBtn = document.getElementById('closeExperienceModal');
  const closeDeleteEntryModalBtn = document.getElementById('closeDeleteEntryModal');
  const closeAdminAuthModalBtn = document.getElementById('closeAdminAuthModal');
  const cancelProjectModalBtn = document.getElementById('cancelProjectModal');
  const cancelExperienceModalBtn = document.getElementById('cancelExperienceModal');
  const cancelDeleteEntryBtn = document.getElementById('cancelDeleteEntry');
  const cancelAdminAuthBtn = document.getElementById('cancelAdminAuth');
  const confirmDeleteEntryBtn = document.getElementById('confirmDeleteEntry');
  const projectNameInput = document.getElementById('projectNameInput');
  const projectSummaryInput = document.getElementById('projectSummaryInput');
  const projectFocusInput = document.getElementById('projectFocusInput');
  const projectTagsInput = document.getElementById('projectTagsInput');
  const projectLinkInput = document.getElementById('projectLinkInput');
  const projectFolderInput = document.getElementById('projectFolderInput');
  const projectFolderSummary = document.getElementById('projectFolderSummary');
  const projectFormError = document.getElementById('projectFormError');
  const experienceTimeInput = document.getElementById('experienceTimeInput');
  const experienceTitleInput = document.getElementById('experienceTitleInput');
  const experienceSummaryInput = document.getElementById('experienceSummaryInput');
  const experienceFormError = document.getElementById('experienceFormError');
  const deleteEntryMessage = document.getElementById('deleteEntryMessage');
  const deleteEntryError = document.getElementById('deleteEntryError');
  const adminPasswordInput = document.getElementById('adminPasswordInput');
  const adminAuthError = document.getElementById('adminAuthError');

  let selectedProjectFolder = '';
  let pendingDeleteEntry = null;
  let lastAdminTrigger = null;
  let siteContent = normalizeSiteContent({
    projects: extractProjectsFromDOM(),
    experiences: extractExperiencesFromDOM()
  });

  function firstDirectChildByTag(node, tagName) {
    return Array.from(node.children).find((child) => child.tagName === tagName.toUpperCase()) || null;
  }

  function normalizeText(value) {
    return typeof value === 'string' ? value.trim() : '';
  }

  function normalizeTags(raw) {
    return raw
      .split(/[，,\n\r]/)
      .map((tag) => tag.trim())
      .filter(Boolean)
      .slice(0, 4);
  }

  function normalizeProject(project) {
    return {
      id: normalizeText(project.id),
      name: normalizeText(project.name),
      summary: normalizeText(project.summary),
      focus: normalizeText(project.focus || project.summary),
      tags: Array.isArray(project.tags) ? project.tags.map((tag) => normalizeText(tag)).filter(Boolean).slice(0, 4) : [],
      link: normalizeText(project.link),
      meta: normalizeText(project.meta),
      featured: Boolean(project.featured),
      custom: Boolean(project.custom)
    };
  }

  function normalizeExperience(experience) {
    return {
      id: normalizeText(experience.id),
      time: normalizeText(experience.time),
      title: normalizeText(experience.title),
      summary: normalizeText(experience.summary),
      custom: Boolean(experience.custom)
    };
  }

  function normalizeSiteContent(content) {
    return {
      projects: Array.isArray(content.projects) ? content.projects.map(normalizeProject).filter((project) => project.id && project.name) : [],
      experiences: Array.isArray(content.experiences) ? content.experiences.map(normalizeExperience).filter((experience) => experience.id && experience.title) : []
    };
  }

  function extractProjectsFromDOM() {
    return Array.from(projectGrid.querySelectorAll('[data-entry-type="project"]')).map((card) => {
      const title = card.querySelector('h3');
      const summary = firstDirectChildByTag(card, 'p');
      const focus = card.querySelector('.sub-block p');
      const meta = card.querySelector('.meta');
      const link = card.querySelector('.btn-primary');
      const tags = Array.from(card.querySelectorAll('.tag-row .tag')).map((tag) => tag.textContent.trim()).filter(Boolean);

      return {
        id: card.dataset.entryId,
        name: title ? title.textContent.trim() : '',
        summary: summary ? summary.textContent.trim() : '',
        focus: focus ? focus.textContent.trim() : '',
        tags,
        link: link ? link.getAttribute('href') : '',
        meta: meta ? meta.textContent.trim() : '',
        featured: card.classList.contains('featured'),
        custom: card.classList.contains('custom-project-card')
      };
    });
  }

  function extractExperiencesFromDOM() {
    return Array.from(experienceTimeline.querySelectorAll('[data-entry-type="experience"]')).map((card) => {
      const time = card.querySelector('.timeline-time');
      const title = card.querySelector('h3');
      const summary = firstDirectChildByTag(card, 'p');

      return {
        id: card.dataset.entryId,
        time: time ? time.textContent.trim() : '',
        title: title ? title.textContent.trim() : '',
        summary: summary ? summary.textContent.trim() : '',
        custom: card.classList.contains('custom-experience-card')
      };
    });
  }

  function createStorageId(value, prefix) {
    const id = value
      .trim()
      .toLowerCase()
      .replace(/\s+/g, '-')
      .replace(/[^\w\u4e00-\u9fa5-]/g, '')
      .replace(/-+/g, '-')
      .replace(/^-+|-+$/g, '');

    return id || (prefix + '-' + Date.now());
  }

  function getAdminToken() {
    return sessionStorage.getItem(ADMIN_TOKEN_KEY) || '';
  }

  function setAdminToken(token) {
    if (token) {
      sessionStorage.setItem(ADMIN_TOKEN_KEY, token);
    } else {
      sessionStorage.removeItem(ADMIN_TOKEN_KEY);
    }
    updateAdminLockUI();
  }

  function isAdminUnlocked() {
    return Boolean(getAdminToken());
  }

  function buildApiUrl(path) {
    return EDITOR_API_BASE ? EDITOR_API_BASE + path : path;
  }

  async function apiRequest(path, options = {}) {
    const headers = {
      'Content-Type': 'application/json',
      ...(options.headers || {})
    };

    if (!options.skipAuth) {
      const token = getAdminToken();
      if (token) {
        headers.Authorization = 'Bearer ' + token;
      }
    }

    const requestInit = {
      method: options.method || 'GET',
      headers
    };

    if (options.body !== undefined) {
      requestInit.body = JSON.stringify(options.body);
    }

    let response;
    try {
      response = await fetch(buildApiUrl(path), requestInit);
    } catch (error) {
      throw new Error('无法连接编辑后端，请确认后端服务已启动，并在 config.js 中配置了正确的 API 地址。');
    }

    const contentType = response.headers.get('content-type') || '';
    let payload = {};

    if (contentType.includes('application/json')) {
      payload = await response.json();
    } else {
      const text = await response.text();
      if (text) {
        payload = { error: text };
      }
    }

    if (!response.ok) {
      let message = payload.error || payload.message || '请求失败。';
      if (response.status === 401) {
        message = '编辑权限已失效，请重新输入密码。';
      }
      if (response.status === 404) {
        message = '未找到编辑后端接口，请确认 config.js 中的 API 地址是否正确。';
      }
      const error = new Error(message);
      error.status = response.status;
      throw error;
    }

    return payload;
  }

  async function verifyAdminPassword(password) {
    return apiRequest('/api/auth/verify', {
      method: 'POST',
      skipAuth: true,
      body: { password }
    });
  }

  async function loadSiteContent() {
    try {
      const response = await fetch(CONTENT_DATA_URL + '?v=' + Date.now(), { cache: 'no-store' });
      if (!response.ok) {
        throw new Error('Failed to load content JSON.');
      }
      const nextContent = await response.json();
      siteContent = normalizeSiteContent(nextContent);
      renderAll();
    } catch (error) {
      renderAll();
      console.warn('Failed to load site content:', error);
    }
  }

  function syncContentFromResponse(payload) {
    if (payload && payload.content) {
      siteContent = normalizeSiteContent(payload.content);
    }
  }

  function createTag(text) {
    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.textContent = text;
    return tag;
  }

  function createDeleteButton(label, adminOnlyClass = 'admin-only') {
    const button = document.createElement('button');
    button.className = adminOnlyClass ? 'btn btn-danger ' + adminOnlyClass : 'btn btn-danger';
    button.type = 'button';
    button.textContent = label;
    button.setAttribute('data-delete-entry', '');
    return button;
  }

  function createProjectCard(project) {
    const card = document.createElement('article');
    card.className = 'card reveal demo-card visible';
    if (project.featured) {
      card.classList.add('featured');
    }
    if (project.custom) {
      card.classList.add('custom-project-card');
    }
    card.dataset.entryId = project.id;
    card.dataset.entryType = 'project';
    card.dataset.entryKind = 'synced';

    const topline = document.createElement('div');
    topline.className = 'card-topline';

    const pill = document.createElement('span');
    pill.className = 'pill';
    pill.textContent = '项目案例';

    const meta = document.createElement('span');
    meta.className = 'meta';
    meta.textContent = project.meta || '项目入口';

    topline.append(pill, meta);

    const title = document.createElement('h3');
    title.textContent = project.name;

    const desc = document.createElement('p');
    desc.textContent = project.summary;

    const subBlock = document.createElement('div');
    subBlock.className = 'sub-block';

    const subTitle = document.createElement('h4');
    subTitle.textContent = '项目重点';

    const subDesc = document.createElement('p');
    subDesc.textContent = project.focus || project.summary;

    subBlock.append(subTitle, subDesc);

    const tagRow = document.createElement('div');
    tagRow.className = 'tag-row';
    (project.tags || []).forEach((tag) => tagRow.appendChild(createTag(tag)));

    const actions = document.createElement('div');
    actions.className = 'actions';

    const viewLink = document.createElement('a');
    viewLink.className = 'btn btn-primary';
    viewLink.href = project.link;
    viewLink.target = '_blank';
    viewLink.rel = 'noopener';
    viewLink.textContent = '查看项目';

    actions.append(viewLink, createDeleteButton('删除项目', 'admin-only'));

    card.append(topline, title, desc, subBlock);
    if ((project.tags || []).length) {
      card.append(tagRow);
    }
    card.append(actions);

    return card;
  }

  function createExperienceCard(experience) {
    const card = document.createElement('article');
    card.className = 'card reveal timeline-card visible';
    if (experience.custom) {
      card.classList.add('custom-experience-card');
    }
    card.dataset.entryId = experience.id;
    card.dataset.entryType = 'experience';
    card.dataset.entryKind = 'synced';

    const time = document.createElement('div');
    time.className = 'timeline-time';
    time.textContent = experience.time;

    const title = document.createElement('h3');
    title.textContent = experience.title;

    const desc = document.createElement('p');
    desc.textContent = experience.summary;

    const actions = document.createElement('div');
    actions.className = 'timeline-actions admin-only-flex';
    actions.appendChild(createDeleteButton('删除经历'));

    card.append(time, title, desc, actions);
    return card;
  }

  function renderProjects() {
    projectGrid.innerHTML = '';
    siteContent.projects.forEach((project) => {
      projectGrid.appendChild(createProjectCard(project));
    });
  }

  function renderExperiences() {
    experienceTimeline.innerHTML = '';
    siteContent.experiences.forEach((experience) => {
      experienceTimeline.appendChild(createExperienceCard(experience));
    });
  }

  function renderAll() {
    renderProjects();
    renderExperiences();
    updateAdminLockUI();
  }

  function syncModalOpenState() {
    const hasOpenModal = Array.from(document.querySelectorAll('.modal-shell')).some((modal) => modal.style.display !== 'none');
    document.body.classList.toggle('modal-open', hasOpenModal);
    document.documentElement.classList.toggle('modal-open', hasOpenModal);
  }

  function setModalOpen(modal, isOpen) {
    modal.hidden = !isOpen;
    modal.style.display = isOpen ? 'grid' : 'none';
    modal.setAttribute('aria-hidden', isOpen ? 'false' : 'true');
    syncModalOpenState();
  }

  function updateAdminLockUI() {
    const unlocked = isAdminUnlocked();
    document.body.dataset.adminAuth = unlocked ? 'true' : 'false';
    adminToggleButton.textContent = unlocked ? '退出编辑' : '解锁编辑';
    adminToggleButton.classList.toggle('is-unlocked', unlocked);
    adminToggleButton.setAttribute('aria-pressed', unlocked ? 'true' : 'false');
  }

  function clearAdminSession() {
    setAdminToken('');
    if (projectModal.style.display !== 'none') {
      closeProjectModal();
    }
    if (experienceModal.style.display !== 'none') {
      closeExperienceModal();
    }
    if (deleteEntryModal.style.display !== 'none') {
      closeDeleteEntryModal();
    }
  }

  function openAdminAuthModal(trigger) {
    lastAdminTrigger = trigger || adminToggleButton;
    adminAuthForm.reset();
    setAdminAuthError('');
    setModalOpen(adminAuthModal, true);
    adminPasswordInput.focus();
  }

  function closeAdminAuthModal() {
    setModalOpen(adminAuthModal, false);
    adminAuthForm.reset();
    setAdminAuthError('');
    if (lastAdminTrigger) {
      lastAdminTrigger.focus();
    }
  }

  function ensureAdminAccess(trigger) {
    if (isAdminUnlocked()) {
      return true;
    }
    openAdminAuthModal(trigger);
    return false;
  }

  function setProjectFormError(message) {
    projectFormError.hidden = !message;
    projectFormError.textContent = message || '';
  }

  function setExperienceFormError(message) {
    experienceFormError.hidden = !message;
    experienceFormError.textContent = message || '';
  }

  function setDeleteEntryError(message) {
    deleteEntryError.hidden = !message;
    deleteEntryError.textContent = message || '';
  }

  function setAdminAuthError(message) {
    adminAuthError.hidden = !message;
    adminAuthError.textContent = message || '';
  }

  function openProjectModal() {
    if (!ensureAdminAccess(openProjectModalBtn)) {
      return;
    }
    setModalOpen(projectModal, true);
    projectNameInput.focus();
  }

  function closeProjectModal() {
    setModalOpen(projectModal, false);
    projectForm.reset();
    selectedProjectFolder = '';
    projectFolderSummary.innerHTML = DEFAULT_PROJECT_FOLDER_SUMMARY;
    setProjectFormError('');
    (isAdminUnlocked() ? openProjectModalBtn : adminToggleButton).focus();
  }

  function openExperienceModal() {
    if (!ensureAdminAccess(openExperienceModalBtn)) {
      return;
    }
    setModalOpen(experienceModal, true);
    experienceTimeInput.focus();
  }

  function closeExperienceModal() {
    setModalOpen(experienceModal, false);
    experienceForm.reset();
    setExperienceFormError('');
    (isAdminUnlocked() ? openExperienceModalBtn : adminToggleButton).focus();
  }

  function setDeleteEntryModalOpen(isOpen) {
    setModalOpen(deleteEntryModal, isOpen);
  }

  function closeDeleteEntryModal() {
    const trigger = pendingDeleteEntry && pendingDeleteEntry.trigger;
    pendingDeleteEntry = null;
    setDeleteEntryModalOpen(false);
    setDeleteEntryError('');
    deleteEntryMessage.textContent = DEFAULT_DELETE_ENTRY_MESSAGE;
    if (trigger && isAdminUnlocked()) {
      trigger.focus();
    }
  }

  function animateCardRemoval(card) {
    return new Promise((resolve) => {
      card.classList.add('is-removing');
      window.setTimeout(resolve, 360);
    });
  }

  function openDeleteEntryModal(card, trigger) {
    if (!ensureAdminAccess(trigger)) {
      return;
    }

    const entryName = (card.querySelector('h3') && card.querySelector('h3').textContent.trim()) || '这项内容';
    const entryLabel = card.dataset.entryType === 'experience' ? '这条经历' : '这个项目';
    pendingDeleteEntry = {
      card,
      trigger,
      entryType: card.dataset.entryType,
      entryId: card.dataset.entryId
    };
    deleteEntryMessage.textContent = '确定要删除“' + entryName + '”' + entryLabel + '吗？确认后会同步到 GitHub 仓库。';
    setDeleteEntryError('');
    setDeleteEntryModalOpen(true);
    confirmDeleteEntryBtn.focus();
  }

  openProjectModalBtn.addEventListener('click', openProjectModal);
  openExperienceModalBtn.addEventListener('click', openExperienceModal);
  closeProjectModalBtn.addEventListener('click', closeProjectModal);
  closeExperienceModalBtn.addEventListener('click', closeExperienceModal);
  cancelProjectModalBtn.addEventListener('click', closeProjectModal);
  cancelExperienceModalBtn.addEventListener('click', closeExperienceModal);
  closeDeleteEntryModalBtn.addEventListener('click', closeDeleteEntryModal);
  cancelDeleteEntryBtn.addEventListener('click', closeDeleteEntryModal);
  closeAdminAuthModalBtn.addEventListener('click', closeAdminAuthModal);
  cancelAdminAuthBtn.addEventListener('click', closeAdminAuthModal);

  adminToggleButton.addEventListener('click', () => {
    if (isAdminUnlocked()) {
      clearAdminSession();
      if (adminAuthModal.style.display !== 'none') {
        closeAdminAuthModal();
      }
      adminToggleButton.focus();
      return;
    }

    openAdminAuthModal(adminToggleButton);
  });

  confirmDeleteEntryBtn.addEventListener('click', async () => {
    if (!pendingDeleteEntry) {
      return;
    }

    const currentEntry = pendingDeleteEntry;
    confirmDeleteEntryBtn.disabled = true;
    cancelDeleteEntryBtn.disabled = true;
    setDeleteEntryError('');

    try {
      const apiPath = currentEntry.entryType === 'experience'
        ? '/api/experiences/' + encodeURIComponent(currentEntry.entryId)
        : '/api/projects/' + encodeURIComponent(currentEntry.entryId);
      const payload = await apiRequest(apiPath, { method: 'DELETE' });

      setDeleteEntryModalOpen(false);
      await animateCardRemoval(currentEntry.card);
      syncContentFromResponse(payload);
      renderAll();
      pendingDeleteEntry = null;
    } catch (error) {
      if (error.status === 401) {
        closeDeleteEntryModal();
        clearAdminSession();
        openAdminAuthModal(currentEntry.trigger);
        setAdminAuthError(error.message);
      } else {
        setDeleteEntryError(error.message);
      }
    } finally {
      confirmDeleteEntryBtn.disabled = false;
      cancelDeleteEntryBtn.disabled = false;
    }
  });

  projectModal.addEventListener('click', (event) => {
    if (event.target === projectModal || event.target.dataset.close === 'project-modal') {
      closeProjectModal();
    }
  });

  experienceModal.addEventListener('click', (event) => {
    if (event.target === experienceModal || event.target.dataset.close === 'experience-modal') {
      closeExperienceModal();
    }
  });

  deleteEntryModal.addEventListener('click', (event) => {
    if (event.target === deleteEntryModal || event.target.dataset.close === 'delete-entry-modal') {
      closeDeleteEntryModal();
    }
  });

  adminAuthModal.addEventListener('click', (event) => {
    if (event.target === adminAuthModal || event.target.dataset.close === 'admin-auth-modal') {
      closeAdminAuthModal();
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && adminAuthModal.style.display !== 'none') {
      closeAdminAuthModal();
    } else if (event.key === 'Escape' && deleteEntryModal.style.display !== 'none') {
      closeDeleteEntryModal();
    } else if (event.key === 'Escape' && experienceModal.style.display !== 'none') {
      closeExperienceModal();
    } else if (event.key === 'Escape' && projectModal.style.display !== 'none') {
      closeProjectModal();
    }
  });

  projectGrid.addEventListener('click', (event) => {
    const deleteBtn = event.target.closest('[data-delete-entry]');
    if (!deleteBtn) {
      return;
    }

    const card = deleteBtn.closest('[data-entry-id]');
    if (!card) {
      return;
    }

    openDeleteEntryModal(card, deleteBtn);
  });

  experienceTimeline.addEventListener('click', (event) => {
    const deleteBtn = event.target.closest('[data-delete-entry]');
    if (!deleteBtn) {
      return;
    }

    const card = deleteBtn.closest('[data-entry-id]');
    if (!card) {
      return;
    }

    openDeleteEntryModal(card, deleteBtn);
  });

  projectFolderInput.addEventListener('change', () => {
    const files = Array.from(projectFolderInput.files || []);
    const entryFile = files.find((file) => /(^|\/)index\.html$/i.test(file.webkitRelativePath || file.name));

    if (!entryFile) {
      selectedProjectFolder = '';
      projectFolderSummary.innerHTML = '未找到 <code>index.html</code>，请重新选择项目目录，或直接填写项目链接。';
      return;
    }

    selectedProjectFolder = (entryFile.webkitRelativePath || entryFile.name).split('/')[0];
    projectFolderSummary.innerHTML = '已选择项目目录：<strong>' + selectedProjectFolder + '</strong>，默认链接将生成为 <code>projects/' + selectedProjectFolder + '/</code>。请确认该目录已经实际放在站点的 <code>projects/</code> 下。';

    if (!projectLinkInput.value.trim()) {
      projectLinkInput.value = 'projects/' + selectedProjectFolder + '/';
    }
  });

  projectForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!isAdminUnlocked()) {
      openAdminAuthModal(openProjectModalBtn);
      return;
    }

    setProjectFormError('');

    const name = projectNameInput.value.trim();
    const summary = projectSummaryInput.value.trim();
    const focus = projectFocusInput.value.trim();
    const tags = normalizeTags(projectTagsInput.value.trim());
    const link = projectLinkInput.value.trim() || (selectedProjectFolder ? 'projects/' + selectedProjectFolder + '/' : '');

    if (!name) {
      setProjectFormError('请填写项目名称。');
      return;
    }

    if (!summary) {
      setProjectFormError('请填写项目简介。');
      return;
    }

    if (!selectedProjectFolder && !link) {
      setProjectFormError('请选择项目文件夹，或手动填写项目链接。');
      return;
    }

    const submitBtn = projectForm.querySelector('button[type="submit"]');
    submitBtn.disabled = true;

    const nextProject = normalizeProject({
      id: selectedProjectFolder || createStorageId(name, 'project'),
      name,
      summary,
      focus,
      tags,
      link,
      meta: selectedProjectFolder ? '自定义项目 / ' + selectedProjectFolder : '自定义项目 / 外部链接',
      featured: false,
      custom: true
    });

    try {
      const payload = await apiRequest('/api/projects', {
        method: 'POST',
        body: { project: nextProject }
      });
      syncContentFromResponse(payload);
      renderAll();
      closeProjectModal();
    } catch (error) {
      if (error.status === 401) {
        clearAdminSession();
        openAdminAuthModal(openProjectModalBtn);
        setAdminAuthError(error.message);
      } else {
        setProjectFormError(error.message);
      }
    } finally {
      submitBtn.disabled = false;
    }
  });

  experienceForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!isAdminUnlocked()) {
      openAdminAuthModal(openExperienceModalBtn);
      return;
    }

    setExperienceFormError('');

    const time = experienceTimeInput.value.trim();
    const title = experienceTitleInput.value.trim();
    const summary = experienceSummaryInput.value.trim();

    if (!time) {
      setExperienceFormError('请填写经历时间。');
      return;
    }

    if (!title) {
      setExperienceFormError('请填写经历标题。');
      return;
    }

    if (!summary) {
      setExperienceFormError('请填写经历简介。');
      return;
    }

    const submitBtn = experienceForm.querySelector('button[type="submit"]');
    submitBtn.disabled = true;

    const nextExperience = normalizeExperience({
      id: createStorageId(title, 'experience'),
      time,
      title,
      summary,
      custom: true
    });

    try {
      const payload = await apiRequest('/api/experiences', {
        method: 'POST',
        body: { experience: nextExperience }
      });
      syncContentFromResponse(payload);
      renderAll();
      closeExperienceModal();
    } catch (error) {
      if (error.status === 401) {
        clearAdminSession();
        openAdminAuthModal(openExperienceModalBtn);
        setAdminAuthError(error.message);
      } else {
        setExperienceFormError(error.message);
      }
    } finally {
      submitBtn.disabled = false;
    }
  });

  adminAuthForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    setAdminAuthError('');

    const password = adminPasswordInput.value;
    if (!password) {
      setAdminAuthError('请输入编辑密码。');
      return;
    }

    const submitBtn = adminAuthForm.querySelector('button[type="submit"]');
    submitBtn.disabled = true;

    try {
      const payload = await verifyAdminPassword(password);
      if (!payload.token) {
        throw new Error('后端没有返回有效的编辑令牌。');
      }
      setAdminToken(payload.token);
      closeAdminAuthModal();
    } catch (error) {
      setAdminAuthError(error.message);
    } finally {
      submitBtn.disabled = false;
    }
  });

  renderAll();
  loadSiteContent();

  window.openProjectModal = openProjectModal;
  window.closeProjectModal = closeProjectModal;
  window.closeExperienceModal = closeExperienceModal;
  window.closeDeleteEntryModal = closeDeleteEntryModal;
  window.closeAdminAuthModal = closeAdminAuthModal;
})();
