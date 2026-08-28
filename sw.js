/* ============================================================================
   Service worker — uniquement utile si l'application est SERVIE par un site
   (Firebase Hosting, intranet, http://localhost…). Il met index.html en cache
   pour que l'adresse reste ouvrable hors connexion et que l'application soit
   installable sur l'écran d'accueil.

   Si index.html est simplement ouvert depuis un dossier local (file://), ce
   fichier est inutile : la page est déjà entièrement autonome.

   Après chaque mise à jour d'index.html, incrémentez le numéro de version
   ci-dessous, sinon les appareils continueront de servir l'ancienne copie.
   ========================================================================= */
const CACHE = 'mise-en-route-v1';
const ACTIFS = ['./', './index.html', './manifest.webmanifest'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => Promise.allSettled(ACTIFS.map(u => c.add(u))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(noms => Promise.all(noms.filter(n => n !== CACHE).map(n => caches.delete(n))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const r = e.request;
  /* on ne touche jamais aux envois vers la Apps Script : ce sont des POST,
     et ils doivent échouer franchement pour que la page les mette en file */
  if (r.method !== 'GET') return;
  if (new URL(r.url).origin !== self.location.origin) return;

  e.respondWith(
    caches.match(r, { ignoreSearch:true }).then(cachee => {
      const reseau = fetch(r).then(res => {
        if (res && res.ok){
          const copie = res.clone();
          e.waitUntil(caches.open(CACHE).then(c => c.put(r, copie)));
        }
        return res;
      }).catch(() => cachee);
      /* cache d'abord (ouverture instantanée, même en zone blanche),
         rafraîchissement en tâche de fond pour la visite suivante */
      return cachee || reseau;
    })
  );
});
