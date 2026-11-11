'use strict';
// Bump this version whenever any app-shell file changes.
const CACHE = 'repair-shell-v1';
const SHELL = ['./index.html', './style.css', './app.js', './pwa.js', './config.js',
  './manifest.webmanifest', './vendor/supabase-2.99.1.js',
  './icons/icon-180.png', './icons/icon-192.png', './icons/icon-512.png'];
const urls = new Set(SHELL.map(path => new URL(path, self.registration.scope).href));
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)));
  // Use the normal waiting lifecycle so updates cannot interrupt a filled form.
});
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.filter(name => name.startsWith('repair-shell-') && name !== CACHE)
      .map(name => caches.delete(name)));
    await self.clients.claim();
  })());
});
self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  // Never intercept database requests, writes, documents or third-party resources.
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;
  const home = new URL('./', self.registration.scope);
  const navigation = request.mode === 'navigate' &&
    (url.pathname === home.pathname || url.pathname === new URL('./index.html', home).pathname);
  if (!navigation && !urls.has(url.href)) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const cached = await cache.match(navigation ? new URL('./index.html', home).href : request);
    return cached || fetch(request);
  })());
});
