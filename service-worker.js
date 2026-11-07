const CACHE_NAME = "food-rescue-connect-shell-v1";
const APP_SHELL = ["/static/manifest.webmanifest", "/static/offline.html", "/static/icons/icon-192.png", "/static/icons/icon-512.png", "/static/icons/icon-512-maskable.png"];
self.addEventListener("install", event => event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(APP_SHELL)).then(() => self.skipWaiting())));
self.addEventListener("activate", event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key)))).then(() => self.clients.claim())));
self.addEventListener("fetch", event => { const req=event.request, url=new URL(req.url); if(req.method!=="GET" || url.origin!==self.location.origin) return; if(req.mode==="navigate") event.respondWith(fetch(req).catch(async()=> (await caches.match("/static/offline.html")) || Response.error())); });
