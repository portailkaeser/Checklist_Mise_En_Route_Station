#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rend index.html totalement autonome (aucune requête réseau au chargement)
   et ajoute une file d'attente d'envoi pour le mode hors connexion."""
import base64, pathlib, sys, re

SRC = pathlib.Path('/mnt/user-data/uploads/index.html')
DL = pathlib.Path('/home/claude/dl')
OUT = pathlib.Path('/home/claude/out/index.html')
OUT.parent.mkdir(parents=True, exist_ok=True)

html = SRC.read_text(encoding='utf-8')

# ---------------------------------------------------------------- polices
FONTS = [
    ("IBM Plex Sans", 'ibm-plex-sans', [400, 500, 600]),
    ("IBM Plex Sans Condensed", 'ibm-plex-sans-condensed', [500, 600, 700]),
    ("IBM Plex Mono", 'ibm-plex-mono', [400, 500, 600]),
]
faces = []
total = 0
for nom, pkg, poids in FONTS:
    for w in poids:
        p = DL / 'f' / pkg / 'package' / 'files' / f'{pkg}-latin-{w}-normal.woff2'
        data = p.read_bytes()
        total += len(data)
        b64 = base64.b64encode(data).decode('ascii')
        faces.append(
            "@font-face{font-family:'%s';font-style:normal;font-weight:%d;font-display:swap;"
            "src:url(data:font/woff2;base64,%s) format('woff2')}" % (nom, w, b64)
        )
print(f"polices : {len(faces)} fichiers, {total/1024:.0f} Kio bruts")

bundle = (DL / 'package' / 'dist' / 'html2pdf.bundle.min.js').read_text(encoding='utf-8')
assert '</script' not in bundle.lower()
print(f"html2pdf : {len(bundle)/1024:.0f} Kio")

# ------------------------------------------------------- remplacement <head>
OLD_HEAD = """<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<!-- génération du PDF envoyé par mail au support technique (bouton « Envoyer au support technique ») -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>"""
assert OLD_HEAD in html, "bloc <head> introuvable"

NEW_HEAD = """<meta name="theme-color" content="#11151A">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black">
<!-- ====================================================================
     FONCTIONNEMENT SANS CONNEXION
     Ce fichier est autonome : polices IBM Plex et bibliothèque html2pdf.js
     sont embarquées ci-dessous. Aucune requête réseau n'est faite à
     l'ouverture, la page se charge donc à l'identique en mode avion, depuis
     une clé USB, un dossier local ou la mémoire du téléphone.
     Seul le bouton « Envoyer au support technique » a besoin d'Internet ;
     hors connexion il met le dossier en file d'attente (voir plus bas).
     ==================================================================== -->
<style id="polices-embarquees">
/* IBM Plex Sans / Sans Condensed / Mono — sous-ensemble latin, woff2 base64
   (source : paquets @fontsource/ibm-plex-*, licence SIL OFL 1.1) */
__FACES__
</style>
<!-- html2pdf.js 0.10.1 (MIT) — génération du PDF dans le navigateur -->
<script id="html2pdf-embarque">__BUNDLE__</script>"""
NEW_HEAD = NEW_HEAD.replace('__FACES__', '\n'.join(faces)).replace('__BUNDLE__', bundle)
html = html.replace(OLD_HEAD, NEW_HEAD, 1)

# ------------------------------------------------------------------- CSS
OLD_CSS = ".mailmsg.bad{color:var(--bad)}"
assert OLD_CSS in html
NEW_CSS = """.mailmsg.bad{color:var(--bad)}
.mailmsg.warn{color:var(--warn)}
/* ---------- état du réseau et file d'attente ---------- */
.net-badge{
  font-family:var(--cond);font-weight:600;font-size:11px;letter-spacing:.07em;text-transform:uppercase;
  padding:4px 10px;border-radius:2px;background:var(--warn-soft);color:#6B4604;white-space:nowrap;
}
.filebar{border-top:1px dashed var(--line);margin-top:2px;padding-top:12px}
.filebar .btn{padding:6px 11px}"""
html = html.replace(OLD_CSS, NEW_CSS, 1)

# --------------------------------------------------------- bandeau : témoin
OLD_TOP = '    <div class="verdict ok" id="verdict"><span class="dot"></span><span id="verdictTxt">À compléter</span></div>'
assert OLD_TOP in html
html = html.replace(
    OLD_TOP,
    OLD_TOP + '\n    <span class="net-badge no-print" id="netBadge" hidden>Hors connexion</span>',
    1)

# ------------------------------------------------------ section 11 : file
OLD_BAR = """      <div class="card-body mailbar" style="padding-top:0">
        <span class="mailmsg" id="mailMsg"></span>
      </div>"""
assert OLD_BAR in html
NEW_BAR = """      <div class="card-body mailbar" style="padding-top:0">
        <span class="mailmsg" id="mailMsg"></span>
      </div>
      <div class="card-body mailbar filebar" id="fileBar" hidden>
        <span class="mailmsg warn" id="fileMsg"></span>
        <button class="btn" id="btnFileEnvoyer">Envoyer maintenant</button>
        <button class="btn" id="btnFileVider">Vider la file</button>
      </div>"""
html = html.replace(OLD_BAR, NEW_BAR, 1)

# --------------------------------------------- module « file d'attente »
ANCRE = """  dossier: ''
};"""
assert ANCRE in html
MODULE = ANCRE + r"""

/* ===================== envoi différé (mode hors connexion) =====================
   Le PDF est fabriqué entièrement dans le navigateur : il est donc disponible
   même sans réseau. Seule sa transmission à la Apps Script exige une
   connexion. Quand celle-ci manque — mode avion, local technique, sous-sol,
   portail captif — le dossier n'est pas perdu : il est rangé dans une file
   d'attente IndexedDB (persistante, y compris après fermeture de l'appareil)
   et reparti automatiquement au retour du réseau, ou à la demande via le
   bouton « Envoyer maintenant ». */

/* POST vers la Apps Script, avec délai maximal et distinction entre panne
   réseau (on met en file) et refus du serveur (on prévient l'utilisateur). */
async function postSupport(payload, delai){
  const ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
  const t = ctrl ? setTimeout(() => ctrl.abort(), delai || 60000) : null;
  let res;
  try{
    res = await fetch(MAIL_CONFIG.url, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain;charset=utf-8' },
      body: JSON.stringify(payload),
      signal: ctrl ? ctrl.signal : undefined
    });
  } catch(e){
    const err = new Error('réseau indisponible'); err.reseau = true; throw err;
  } finally { if (t) clearTimeout(t); }
  if (!res.ok){
    const err = new Error('serveur injoignable (HTTP ' + res.status + ')');
    err.reseau = true;                                  // 4xx/5xx : on retentera
    throw err;
  }
  let d;
  try { d = await res.json(); }
  catch(e){ const err = new Error('réponse illisible du serveur'); err.reseau = true; throw err; }
  if (!d.ok) throw new Error(d.erreur || "Échec de l'envoi.");   // refus explicite : définitif
  return d;
}

/* file persistante ; repli en mémoire si IndexedDB est refusée
   (navigation privée de certains navigateurs) */
const FileEnvoi = (() => {
  const NOM = 'mer-file-envoi', ST = 'envois';
  let memoire = [], seqMem = 1, dispo = ('indexedDB' in window);
  const req = r => new Promise((res, rej) => { r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); });
  function ouvrir(){
    return new Promise((res, rej) => {
      const r = indexedDB.open(NOM, 1);
      r.onupgradeneeded = () => {
        const d = r.result;
        if (!d.objectStoreNames.contains(ST)) d.createObjectStore(ST, { keyPath:'id', autoIncrement:true });
      };
      r.onsuccess = () => res(r.result);
      r.onerror = () => rej(r.error);
      r.onblocked = () => rej(new Error('base verrouillée'));
    });
  }
  async function tx(mode, action){
    if (!dispo) throw new Error('indexedDB indisponible');
    const d = await ouvrir();
    try { return await action(d.transaction(ST, mode).objectStore(ST)); }
    finally { setTimeout(() => d.close(), 0); }
  }
  return {
    persistante(){ return dispo; },
    async ajouter(payload, libelle){
      const item = { payload, libelle, date: new Date().toISOString() };
      try { return await tx('readwrite', s => req(s.add(item))); }
      catch(e){ dispo = false; item.id = seqMem++; memoire.push(item); return item.id; }
    },
    async lister(){
      try { return await tx('readonly', s => req(s.getAll())); }
      catch(e){ dispo = false; return memoire.slice(); }
    },
    async retirer(id){
      try { return await tx('readwrite', s => req(s.delete(id))); }
      catch(e){ memoire = memoire.filter(i => i.id !== id); }
    },
    async vider(){
      memoire = [];
      try { return await tx('readwrite', s => req(s.clear())); } catch(e){}
    }
  };
})();

/* ---------- affichage de l'état ---------- */
function majBandeauReseau(){
  const b = $('#netBadge');
  if (b) b.hidden = (navigator.onLine !== false);
}

async function majFileUI(texte){
  const bar = $('#fileBar'), msg = $('#fileMsg');
  if (!bar || !msg) return 0;
  const n = (await FileEnvoi.lister()).length;
  bar.hidden = (n === 0);
  if (n){
    msg.textContent = texte || (
      n + (n > 1 ? ' dossiers en attente d\u2019envoi' : ' dossier en attente d\u2019envoi')
      + (navigator.onLine === false
          ? ' \u2014 d\u00e9part automatique au retour du r\u00e9seau.'
          : ' \u2014 nouvelle tentative en cours\u2026')
      + (FileEnvoi.persistante() ? '' : ' (file non persistante : ne fermez pas la page)')
    );
  } else if (texte){
    bar.hidden = false;
    msg.textContent = texte;
  }
  return n;
}

/* ---------- vidage de la file ---------- */
let videEnCours = false;
async function viderFileEnvoi(manuel){
  if (videEnCours) return;
  const items = await FileEnvoi.lister();
  if (!items.length){ await majFileUI(); return; }
  if (navigator.onLine === false){
    await majFileUI(items.length + ' dossier(s) en attente \u2014 toujours hors connexion.');
    return;
  }
  videEnCours = true;
  let envoyes = 0, souci = '';
  try{
    for (const it of items){
      try {
        await postSupport(it.payload);
        await FileEnvoi.retirer(it.id);
        envoyes++;
      } catch(e){
        if (e && e.reseau){ souci = 'r\u00e9seau'; break; }        // on retentera plus tard
        await FileEnvoi.retirer(it.id);                            // refus définitif : on évacue
        souci = 'Dossier refus\u00e9 par le serveur (' + (e.message || 'erreur') + ') \u2014 retir\u00e9 de la file, utilisez « Imprimer / PDF ».';
        break;
      }
    }
  } finally { videEnCours = false; }

  const reste = (await FileEnvoi.lister()).length;
  let txt = '';
  if (envoyes) txt = envoyes + ' dossier(s) envoy\u00e9(s) au support technique.';
  if (souci === 'r\u00e9seau') txt = (txt ? txt + ' ' : '') + reste + ' en attente : connexion toujours indisponible.';
  else if (souci) txt = (txt ? txt + ' ' : '') + souci;
  else if (!reste && !envoyes && manuel) txt = 'Rien \u00e0 envoyer.';
  await majFileUI(txt || undefined);
  if (envoyes && !reste){
    const m = $('#fileMsg'); if (m){ m.className = 'mailmsg ok'; setTimeout(() => { const b = $('#fileBar'); if (b && !reste) b.hidden = true; }, 6000); }
  } else {
    const m = $('#fileMsg'); if (m) m.className = 'mailmsg warn';
  }
}

function surveillerReseau(){
  majBandeauReseau();
  window.addEventListener('online',  () => { majBandeauReseau(); viderFileEnvoi(false); });
  window.addEventListener('offline', () => { majBandeauReseau(); majFileUI(); });
  /* certains Android ne déclenchent pas « online » de façon fiable :
     on retente aussi périodiquement tant qu'il reste des dossiers en file */
  setInterval(() => { if (navigator.onLine !== false) viderFileEnvoi(false); }, 120000);
}"""
html = html.replace(ANCRE, MODULE, 1)

# --------------------------------------- envoyerSupport : envoi ou mise en file
OLD_FETCH = """    const res = await fetch(MAIL_CONFIG.url, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain;charset=utf-8' },
      body: JSON.stringify(payload)
    });
    const d = await res.json();
    if (!d.ok) throw new Error(d.erreur || 'Échec de l\\'envoi.');

    msg.textContent = 'Envoyé au service support technique' + (d.lien ? ' (archivé sur le Drive).' : '.');
    msg.classList.add('ok');"""
assert OLD_FETCH in html, "bloc fetch introuvable"
NEW_FETCH = """    /* hors connexion : on range le dossier dans la file, il partira seul */
    if (navigator.onLine === false){
      await FileEnvoi.ajouter(payload, client);
      msg.textContent = "Hors connexion : le dossier est enregistré et sera envoyé automatiquement dès le retour du réseau.";
      msg.classList.add('warn');
      await majFileUI();
      return;
    }

    let d;
    try {
      d = await postSupport(payload);
    } catch(eNet){
      if (eNet && eNet.reseau){
        await FileEnvoi.ajouter(payload, client);
        msg.textContent = "Connexion indisponible : le dossier est enregistré et sera envoyé automatiquement dès que le réseau reviendra.";
        msg.classList.add('warn');
        await majFileUI();
        return;
      }
      throw eNet;
    }

    msg.textContent = 'Envoyé au service support technique' + (d.lien ? ' (archivé sur le Drive).' : '.');
    msg.classList.add('ok');"""
html = html.replace(OLD_FETCH, NEW_FETCH, 1)

# le message d'erreur « bibliothèque non chargée » n'a plus lieu d'être
html = html.replace(
    'throw new Error("bibliothèque PDF non chargée (le fichier doit être ouvert une première fois avec une connexion internet).");',
    'throw new Error("bibliothèque PDF non chargée : le fichier index.html a été tronqué ou modifié, récupérez-en une copie intacte.");',
    1)

# ------------------------------------------------------------- branchements
OLD_WIRE = "  $('#btnMail').onclick = envoyerSupport;"
assert OLD_WIRE in html
html = html.replace(OLD_WIRE, OLD_WIRE + """
  $('#btnFileEnvoyer').onclick = () => viderFileEnvoi(true);
  $('#btnFileVider').onclick = async () => {
    if (!confirm('Supprimer définitivement les dossiers en attente d\\'envoi ?')) return;
    await FileEnvoi.vider();
    await majFileUI();
    $('#fileBar').hidden = true;
  };""", 1)

OLD_INIT = """  paint(); wire(); admWire(); go('station');
  $('#saveState').textContent = raw ? 'Dossier restauré' : 'Nouveau dossier';"""
assert OLD_INIT in html
html = html.replace(OLD_INIT, """  paint(); wire(); admWire(); go('station');
  $('#saveState').textContent = raw ? 'Dossier restauré' : 'Nouveau dossier';
  /* état du réseau + reprise des envois différés */
  surveillerReseau();
  await majFileUI();
  viderFileEnvoi(false);
  /* si le fichier est servi par un site (http/https) plutôt qu'ouvert en
     local, on enregistre un service worker pour que l'adresse reste
     accessible hors connexion. Absent ou en échec : sans conséquence. */
  if (/^https?:$/.test(location.protocol)){
    const lien = document.createElement('link');
    lien.rel = 'manifest'; lien.href = 'manifest.webmanifest';
    document.head.appendChild(lien);
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});
  }""", 1)

OUT.write_text(html, encoding='utf-8')
print(f"écrit : {OUT}  ({OUT.stat().st_size/1024/1024:.2f} Mio)")
