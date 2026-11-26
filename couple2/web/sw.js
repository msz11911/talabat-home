/* Service Worker: يحفظ واجهة التطبيق للفتح السريع والعمل بدون اتصال.
   البيانات والصور تحتاج اتصالاً بالسيرفر. */
const CACHE = "talabat-home-v10";
const SHELL = [
  "./", "index.html", "styles.css", "config.js", "app.js",
  "manifest.webmanifest", "talabat_chime.wav",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET" || new URL(request.url).origin !== self.location.origin) return;
  if (request.url.includes("/api/")) return; // البيانات دائماً من الشبكة

  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response.ok) caches.open(CACHE).then((cache) => cache.put(request, response.clone()));
        return response;
      })
      .catch(async () => (await caches.match(request)) || caches.match("./index.html"))
  );
});
