const CACHE='spicypy-v2';
const STATIC=['/manifest.webmanifest','/static/icon.svg'];

self.addEventListener('install',event=>{
  event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(STATIC)));
  self.skipWaiting();
});

self.addEventListener('activate',event=>{
  event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener('fetch',event=>{
  const req=event.request;
  if(req.method!=='GET') return;

  const url=new URL(req.url);
  if(req.mode==='navigate' || url.pathname.startsWith('/api/') || url.pathname==='/private-login' || url.pathname==='/logout'){
    event.respondWith(fetch(req));
    return;
  }

  if(STATIC.includes(url.pathname)){
    event.respondWith(caches.match(req).then(hit=>hit||fetch(req)));
  }
});
