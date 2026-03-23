const textEncoder = new TextEncoder();
const textDecoder = new TextDecoder();

class HttpError extends Error {
  constructor(message, status = 500, details = {}) {
    super(message);
    this.name = 'HttpError';
    this.status = status;
    this.details = details;
  }
}

function normalizeText(value) {
  return typeof value === 'string' ? value.trim() : '';
}

function normalizeProject(project) {
  const tags = Array.isArray(project?.tags) ? project.tags : [];
  return {
    id: normalizeText(project?.id),
    name: normalizeText(project?.name),
    summary: normalizeText(project?.summary),
    focus: normalizeText(project?.focus || project?.summary),
    tags: tags.map((tag) => normalizeText(tag)).filter(Boolean).slice(0, 4),
    link: normalizeText(project?.link),
    meta: normalizeText(project?.meta),
    featured: Boolean(project?.featured),
    custom: Boolean(project?.custom)
  };
}

function normalizeExperience(experience) {
  return {
    id: normalizeText(experience?.id),
    time: normalizeText(experience?.time),
    title: normalizeText(experience?.title),
    summary: normalizeText(experience?.summary),
    custom: Boolean(experience?.custom)
  };
}

function normalizeContent(content) {
  const projects = Array.isArray(content?.projects) ? content.projects : [];
  const experiences = Array.isArray(content?.experiences) ? content.experiences : [];
  return {
    projects: projects
      .map((project) => normalizeProject(project))
      .filter((project) => project.id && project.name),
    experiences: experiences
      .map((experience) => normalizeExperience(experience))
      .filter((experience) => experience.id && experience.title)
  };
}

function parseAllowedOrigins(rawValue) {
  return String(rawValue || '*')
    .split(',')
    .map((origin) => origin.trim())
    .filter(Boolean);
}

function isOriginAllowed(origin, allowedOrigins) {
  if (!origin) {
    return true;
  }
  return allowedOrigins.includes('*') || allowedOrigins.includes(origin);
}

function buildCorsHeaders(origin, allowedOrigins) {
  const headers = {
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
    'Access-Control-Max-Age': '86400'
  };

  if (allowedOrigins.includes('*')) {
    headers['Access-Control-Allow-Origin'] = '*';
  } else if (origin && allowedOrigins.includes(origin)) {
    headers['Access-Control-Allow-Origin'] = origin;
    headers.Vary = 'Origin';
  }

  return headers;
}

function jsonResponse(payload, status, request, env) {
  const origin = request.headers.get('Origin') || '';
  const allowedOrigins = parseAllowedOrigins(env.EDITOR_ALLOWED_ORIGINS);
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      ...buildCorsHeaders(origin, allowedOrigins),
      'Content-Type': 'application/json; charset=utf-8'
    }
  });
}

function requireConfig(env) {
  const missing = [];
  if (!env.GITHUB_TOKEN) {
    missing.push('GITHUB_TOKEN');
  }
  if (!env.GITHUB_OWNER) {
    missing.push('GITHUB_OWNER');
  }
  if (!env.GITHUB_REPO) {
    missing.push('GITHUB_REPO');
  }
  if (!env.EDITOR_PASSWORD && !env.EDITOR_PASSWORD_HASH) {
    missing.push('EDITOR_PASSWORD or EDITOR_PASSWORD_HASH');
  }
  if (!env.EDITOR_TOKEN_SECRET) {
    missing.push('EDITOR_TOKEN_SECRET');
  }
  if (missing.length) {
    throw new HttpError('Cloudflare Worker 缺少必要配置：' + missing.join(', '), 500);
  }
}

function timingSafeEqual(left, right) {
  if (left.length !== right.length) {
    return false;
  }
  let mismatch = 0;
  for (let index = 0; index < left.length; index += 1) {
    mismatch |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return mismatch === 0;
}

async function sha256Hex(value) {
  const digest = await crypto.subtle.digest('SHA-256', textEncoder.encode(value));
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
}

async function passwordIsValid(password, env) {
  if (env.EDITOR_PASSWORD_HASH) {
    const nextHash = await sha256Hex(password);
    return timingSafeEqual(nextHash, String(env.EDITOR_PASSWORD_HASH).trim().toLowerCase());
  }
  return timingSafeEqual(password, String(env.EDITOR_PASSWORD || '').trim());
}

function bytesToBase64(bytes) {
  let binary = '';
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}

function base64ToBytes(value) {
  const binary = atob(value);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

function encodeBase64Url(input) {
  const bytes = typeof input === 'string' ? textEncoder.encode(input) : input;
  return bytesToBase64(bytes).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

function decodeBase64Url(value) {
  const padded = value.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(value.length / 4) * 4, '=');
  return base64ToBytes(padded);
}

async function signText(secret, payload) {
  const key = await crypto.subtle.importKey(
    'raw',
    textEncoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const signature = await crypto.subtle.sign('HMAC', key, textEncoder.encode(payload));
  return new Uint8Array(signature);
}

async function createSessionToken(env) {
  const ttlSeconds = Number.parseInt(env.EDITOR_TOKEN_TTL_SECONDS || '43200', 10);
  const expiresAt = Math.floor(Date.now() / 1000) + ttlSeconds;
  const payloadPart = encodeBase64Url(JSON.stringify({ exp: expiresAt }));
  const signaturePart = encodeBase64Url(await signText(env.EDITOR_TOKEN_SECRET, payloadPart));
  return {
    token: payloadPart + '.' + signaturePart,
    expiresAt
  };
}

async function validateSessionToken(token, env) {
  const [payloadPart, signaturePart] = String(token || '').split('.', 2);
  if (!payloadPart || !signaturePart) {
    return false;
  }

  const expectedSignature = encodeBase64Url(await signText(env.EDITOR_TOKEN_SECRET, payloadPart));
  if (!timingSafeEqual(signaturePart, expectedSignature)) {
    return false;
  }

  try {
    const payload = JSON.parse(textDecoder.decode(decodeBase64Url(payloadPart)));
    return Number(payload.exp || 0) > Math.floor(Date.now() / 1000);
  } catch (error) {
    return false;
  }
}

async function githubRequest(env, method, path, body) {
  const response = await fetch('https://api.github.com' + path, {
    method,
    headers: {
      Accept: 'application/vnd.github+json',
      Authorization: 'Bearer ' + env.GITHUB_TOKEN,
      'Content-Type': 'application/json',
      'User-Agent': 'portfolio-editor-cloudflare-worker',
      'X-GitHub-Api-Version': '2022-11-28'
    },
    body: body === undefined ? undefined : JSON.stringify(body)
  });

  const rawText = await response.text();
  let payload = {};
  if (rawText) {
    try {
      payload = JSON.parse(rawText);
    } catch (error) {
      payload = { message: rawText };
    }
  }

  if (!response.ok) {
    const githubMessage = payload.message || 'GitHub request failed';

    if (response.status === 401 || response.status === 403) {
      throw new HttpError('GitHub 令牌无效或权限不足，请检查 Worker Secret: GITHUB_TOKEN。', 500, {
        githubStatus: response.status,
        githubMessage
      });
    }

    if (response.status === 404 && path.includes('/contents/')) {
      throw new HttpError(
        '未在 GitHub 仓库中找到 ' + (env.EDITOR_CONTENT_PATH || 'data/site-content.json') + '，请先把这个文件推送到目标分支。',
        500,
        {
          githubStatus: response.status,
          githubMessage
        }
      );
    }

    throw new HttpError(githubMessage, 500, {
      githubStatus: response.status,
      githubMessage
    });
  }

  return payload;
}

async function readRepoContent(env) {
  const contentPath = encodeURIComponent(env.EDITOR_CONTENT_PATH || 'data/site-content.json').replace(/%2F/g, '/');
  const branch = encodeURIComponent(env.GITHUB_BRANCH || 'main');
  const payload = await githubRequest(
    env,
    'GET',
    '/repos/' + env.GITHUB_OWNER + '/' + env.GITHUB_REPO + '/contents/' + contentPath + '?ref=' + branch
  );
  const rawContent = String(payload.content || '').replace(/\n/g, '');
  const decodedContent = textDecoder.decode(base64ToBytes(rawContent));
  return {
    content: normalizeContent(JSON.parse(decodedContent)),
    sha: payload.sha
  };
}

async function writeRepoContent(env, content, sha, message) {
  const contentPath = encodeURIComponent(env.EDITOR_CONTENT_PATH || 'data/site-content.json').replace(/%2F/g, '/');
  const normalizedContent = normalizeContent(content);
  const body = {
    message,
    branch: env.GITHUB_BRANCH || 'main',
    content: bytesToBase64(textEncoder.encode(JSON.stringify(normalizedContent, null, 2)))
  };

  if (sha) {
    body.sha = sha;
  }

  await githubRequest(
    env,
    'PUT',
    '/repos/' + env.GITHUB_OWNER + '/' + env.GITHUB_REPO + '/contents/' + contentPath,
    body
  );
}

async function requireAuthorization(request, env) {
  const authHeader = request.headers.get('Authorization') || '';
  if (!authHeader.startsWith('Bearer ')) {
    throw new HttpError('Missing editor token.', 401);
  }

  const token = authHeader.slice(7).trim();
  const isValid = await validateSessionToken(token, env);
  if (!isValid) {
    throw new HttpError('Invalid or expired editor token.', 401);
  }
}

async function readJsonBody(request) {
  try {
    return await request.json();
  } catch (error) {
    throw new HttpError('Invalid JSON body.', 400);
  }
}

async function upsertProject(env, project) {
  const nextProject = normalizeProject(project);
  if (!nextProject.id || !nextProject.name || !nextProject.summary || !nextProject.link) {
    throw new HttpError('Project id, name, summary, and link are required.', 400);
  }

  const { content, sha } = await readRepoContent(env);
  const existingIndex = content.projects.findIndex((item) => item.id === nextProject.id);
  if (existingIndex >= 0) {
    content.projects[existingIndex] = nextProject;
  } else {
    content.projects.push(nextProject);
  }

  await writeRepoContent(env, content, sha, 'Update project ' + nextProject.name + ' via portfolio editor');
  return (await readRepoContent(env)).content;
}

async function deleteProject(env, projectId) {
  const { content, sha } = await readRepoContent(env);
  const removedProject = content.projects.find((project) => project.id === projectId);
  if (!removedProject) {
    throw new HttpError('Project not found.', 404);
  }

  content.projects = content.projects.filter((project) => project.id !== projectId);
  await writeRepoContent(env, content, sha, 'Delete project ' + removedProject.name + ' via portfolio editor');
  return (await readRepoContent(env)).content;
}

async function upsertExperience(env, experience) {
  const nextExperience = normalizeExperience(experience);
  if (!nextExperience.id || !nextExperience.time || !nextExperience.title || !nextExperience.summary) {
    throw new HttpError('Experience id, time, title, and summary are required.', 400);
  }

  const { content, sha } = await readRepoContent(env);
  const existingIndex = content.experiences.findIndex((item) => item.id === nextExperience.id);
  if (existingIndex >= 0) {
    content.experiences[existingIndex] = nextExperience;
  } else {
    content.experiences.push(nextExperience);
  }

  await writeRepoContent(env, content, sha, 'Update experience ' + nextExperience.title + ' via portfolio editor');
  return (await readRepoContent(env)).content;
}

async function deleteExperience(env, experienceId) {
  const { content, sha } = await readRepoContent(env);
  const removedExperience = content.experiences.find((experience) => experience.id === experienceId);
  if (!removedExperience) {
    throw new HttpError('Experience not found.', 404);
  }

  content.experiences = content.experiences.filter((experience) => experience.id !== experienceId);
  await writeRepoContent(env, content, sha, 'Delete experience ' + removedExperience.title + ' via portfolio editor');
  return (await readRepoContent(env)).content;
}

async function handleApiRequest(request, env) {
  requireConfig(env);

  const url = new URL(request.url);
  const method = request.method.toUpperCase();

  if (method === 'GET' && url.pathname === '/api/health') {
    return jsonResponse(
      {
        ok: true,
        mode: 'cloudflare-worker',
        branch: env.GITHUB_BRANCH || 'main',
        contentPath: env.EDITOR_CONTENT_PATH || 'data/site-content.json'
      },
      200,
      request,
      env
    );
  }

  if (method === 'GET' && url.pathname === '/api/content') {
    const { content } = await readRepoContent(env);
    return jsonResponse({ ok: true, content }, 200, request, env);
  }

  if (method === 'POST' && url.pathname === '/api/auth/verify') {
    const body = await readJsonBody(request);
    const password = normalizeText(body.password);
    if (!password || !(await passwordIsValid(password, env))) {
      throw new HttpError('密码不正确。', 401);
    }
    const session = await createSessionToken(env);
    return jsonResponse({ ok: true, token: session.token, expiresAt: session.expiresAt }, 200, request, env);
  }

  await requireAuthorization(request, env);

  if (method === 'POST' && url.pathname === '/api/projects') {
    const body = await readJsonBody(request);
    const content = await upsertProject(env, body.project || {});
    return jsonResponse({ ok: true, content }, 200, request, env);
  }

  if (method === 'POST' && url.pathname === '/api/experiences') {
    const body = await readJsonBody(request);
    const content = await upsertExperience(env, body.experience || {});
    return jsonResponse({ ok: true, content }, 200, request, env);
  }

  if (method === 'DELETE' && url.pathname.startsWith('/api/projects/')) {
    const projectId = decodeURIComponent(url.pathname.slice('/api/projects/'.length));
    const content = await deleteProject(env, projectId);
    return jsonResponse({ ok: true, content }, 200, request, env);
  }

  if (method === 'DELETE' && url.pathname.startsWith('/api/experiences/')) {
    const experienceId = decodeURIComponent(url.pathname.slice('/api/experiences/'.length));
    const content = await deleteExperience(env, experienceId);
    return jsonResponse({ ok: true, content }, 200, request, env);
  }

  throw new HttpError('Route not found.', 404);
}

export default {
  async fetch(request, env) {
    const allowedOrigins = parseAllowedOrigins(env.EDITOR_ALLOWED_ORIGINS);
    const origin = request.headers.get('Origin') || '';

    if (!isOriginAllowed(origin, allowedOrigins)) {
      return jsonResponse({ error: 'Origin is not allowed.' }, 403, request, env);
    }

    if (request.method.toUpperCase() === 'OPTIONS') {
      return new Response(null, {
        status: 204,
        headers: buildCorsHeaders(origin, allowedOrigins)
      });
    }

    try {
      return await handleApiRequest(request, env);
    } catch (error) {
      const status = error instanceof HttpError ? error.status : 500;
      const message = error instanceof Error ? error.message : 'Internal Server Error';
      return jsonResponse({ error: message }, status, request, env);
    }
  }
};
