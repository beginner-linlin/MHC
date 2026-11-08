#!/usr/bin/env node
/**
 * MHC 预测工作台 —— Windows 侧反向代理
 *
 * 作用：把 WSL 内 Flask（127.0.0.1:8008）暴露到局域网（0.0.0.0:8080）。
 * 之所以在 Windows 侧再套一层，是因为 WSL 的 NAT 网络无法被局域网直接访问，
 * 而 C:\AI\node.exe 已有一条现成的 Windows 防火墙入站放行规则（无需管理员权限）。
 *
 * 用法：
 *   node server.js
 * 环境变量：
 *   MHC_PROXY_PORT   监听端口，默认 8080
 *   MHC_PROXY_HOST   监听地址，默认 0.0.0.0
 *   MHC_BACKEND      后端地址，默认 http://127.0.0.1:8008
 */

'use strict';

const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { URL } = require('node:url');

const PORT = Number(process.env.MHC_PROXY_PORT || 8080);
const HOST = process.env.MHC_PROXY_HOST || '0.0.0.0';
const TARGET = new URL(process.env.MHC_BACKEND || 'http://127.0.0.1:8008');
const LOG_DIR = process.env.MHC_LOG_DIR || path.join(__dirname, 'logs');
const LOG_FILE = path.join(LOG_DIR, 'proxy.log');

fs.mkdirSync(LOG_DIR, { recursive: true });

// ─────────────────────────────── 日志 ───────────────────────────────

let logStream = null;
try {
  logStream = fs.createWriteStream(LOG_FILE, { flags: 'a' });
} catch {
  logStream = null;
}

function log(line) {
  const stamp = new Date().toLocaleTimeString('zh-CN', { hour12: false });
  const text = `[${stamp}] ${line}`;
  process.stdout.write(text + '\n');
  if (logStream) logStream.write(text + '\n');
}

function rotateIfHuge() {
  try {
    const st = fs.statSync(LOG_FILE);
    if (st.size > 8 * 1024 * 1024) {
      fs.renameSync(LOG_FILE, LOG_FILE + '.1');
      if (logStream) logStream.end();
      logStream = fs.createWriteStream(LOG_FILE, { flags: 'a' });
    }
  } catch {
    /* 忽略 */
  }
}

// ─────────────────────────────── 服务 ───────────────────────────────

const ERROR_PAGE = (msg) => `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>后端未就绪</title>
<style>
  body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
       font:15px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;background:#f4f6f9;color:#1f2937}
  .box{background:#fff;padding:36px 44px;border-radius:14px;box-shadow:0 6px 28px rgba(15,40,80,.10);max-width:560px}
  h1{margin:0 0 6px;font-size:20px;color:#1e5aa8}
  p{margin:8px 0;color:#4b5563}
  code{background:#eef2f7;padding:2px 6px;border-radius:4px;font-family:Consolas,monospace;font-size:13px}
  .hint{margin-top:18px;padding:12px 16px;background:#fff8e6;border-left:3px solid #d4a017;border-radius:4px;font-size:13px}
</style></head><body><div class="box">
<h1>后端服务暂时不可用</h1>
<p>${msg}</p>
<p>代理仍在运行，正在等待 WSL 内的 MHC 后端启动。</p>
<div class="hint">
请确认：<br>
1. WSL 发行版 <code>Ubuntu-24.04</code> 已启动（命令 <code>wsl -d Ubuntu-24.04 -- echo ok</code>）<br>
2. 后端已运行（命令 <code>wsl -d Ubuntu-24.04 -- bash /opt/bio/app/start_backend.sh status</code>）<br>
3. 稍等 3–5 秒后刷新本页
</div></div></body></html>`;

function sendError(res, status, message) {
  const html = ERROR_PAGE(message);
  res.writeHead(status, {
    'Content-Type': 'text/html; charset=utf-8',
    'Content-Length': Buffer.byteLength(html),
    'Cache-Control': 'no-store',
  });
  res.end(html);
}

function clientIp(req) {
  return (req.socket.remoteAddress || '').replace(/^::ffff:/, '');
}

const server = http.createServer((req, res) => {
  const started = Date.now();
  const ip = clientIp(req);

  // 代理自身的健康检查（不转发）
  if (req.url === '/__proxy/health') {
    const body = JSON.stringify({
      ok: true,
      role: 'proxy',
      pid: process.pid,
      listen: `${HOST}:${PORT}`,
      backend: TARGET.href,
      uptime_s: Math.round(process.uptime()),
    });
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(body);
    return;
  }

  const chunks = [];
  req.on('data', (c) => {
    chunks.push(c);
    if (Buffer.concat(chunks).length > 64 * 1024 * 1024) req.destroy();
  });
  req.on('error', () => {});

  req.on('end', () => {
    const payload = chunks.length ? Buffer.concat(chunks) : null;

    const headers = { ...req.headers };
    headers.host = TARGET.host;
    headers['x-forwarded-for'] = ip;
    headers['x-forwarded-proto'] = 'http';
    headers['x-forwarded-host'] = req.headers.host || '';
    headers['accept-encoding'] = 'identity'; // 不做二次压缩，避免导出文件损坏
    if (payload) headers['content-length'] = String(payload.length);
    else delete headers['content-length'];

    const options = {
      protocol: TARGET.protocol,
      hostname: TARGET.hostname,
      port: TARGET.port || 80,
      method: req.method,
      path: req.url,
      headers,
    };

    const upstream = http.request(options, (up) => {
      const outHeaders = { ...up.headers };
      delete outHeaders.connection;
      delete outHeaders['keep-alive'];
      delete outHeaders['transfer-encoding'];
      res.writeHead(up.statusCode || 502, outHeaders);
      up.pipe(res);

      const ms = Date.now() - started;
      const size = up.headers['content-length'] || '-';
      log(
        `${ip} ${req.method} ${decodeURIComponent(req.url)} -> ${up.statusCode} ${size}B ${ms}ms`
      );
    });

    upstream.setTimeout(30 * 60 * 1000, () => {
      upstream.destroy(new Error('上游超时'));
    });

    upstream.on('error', (err) => {
      const ms = Date.now() - started;
      log(`${ip} ${req.method} ${req.url} -> 502 (${err.code || err.message}) ${ms}ms`);
      if (!res.headersSent) {
        sendError(
          res,
          502,
          `无法连接后端 <code>${TARGET.href}</code>（${err.code || err.message}）。`
        );
      } else {
        res.destroy();
      }
    });

    if (payload) upstream.write(payload);
    upstream.end();

    rotateIfHuge();
  });
});

server.on('error', (err) => {
  if (err.code === 'EADDRINUSE') {
    log(`端口 ${PORT} 已被占用，代理未启动。`);
    process.exit(2);
  }
  log(`代理错误：${err.message}`);
  process.exit(1);
});

server.listen(PORT, HOST, () => {
  log(`MHC 反向代理已启动：http://${HOST}:${PORT}  ->  ${TARGET.href}  (pid ${process.pid})`);
});

function shutdown(sig) {
  log(`收到 ${sig}，正在关闭代理…`);
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(0), 3000);
}
process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
