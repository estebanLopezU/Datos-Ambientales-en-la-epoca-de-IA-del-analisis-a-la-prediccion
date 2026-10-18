// 21_probar_zoom_mapa.js - Prueba del zoom al hacer click en un marcador.
//
// Verifica que, al hacer click en el marcador de La Nubia, el mapa se centre
// en sus coordenadas (dLat/dLon ~ 0) y suba el zoom a >= 16.
//
// Requisitos:
//   1. El servidor Django corriendo:  python manage.py runserver 0.0.0.0:5000
//   2. Node + dependencias:           cd scripts && npm install
//   3. Navegador Chromium de Playwright: npx playwright install chromium
// Ejecutar:  node 21_probar_zoom_mapa.js   (o  npm test)
//
// Engancha L.Map.prototype.setView (sin tocar el codigo de la app) para leer
// la instancia del mapa y los argumentos que recibe el handler del marcador.


const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const logs = [];
  page.on('console', (m) => logs.push(m.type() + ': ' + m.text()));
  page.on('pageerror', (e) => logs.push('pageerror: ' + String(e)));

  // Antes de que corra cualquier script de la pagina, engancha L.Map.prototype.setView
  // (espera a que cargue Leaflet desde el CDN). Captura la instancia del mapa y los args.
  await page.addInitScript(() => {
    window.__calls = [];
    const hook = () => {
      if (window.L && window.L.Map && !window.L.Map.prototype.setView.__hooked) {
        const orig = window.L.Map.prototype.setView;
        window.L.Map.prototype.setView = function (center, zoom, opts) {
          window.__map = this;
          window.__calls.push({ center: [center[0], center[1]], zoom, animate: !!(opts && opts.animate) });
          return orig.call(this, center, zoom, opts);
        };
        window.L.Map.prototype.setView.__hooked = true;
      } else if (!window.L) {
        setTimeout(hook, 10);
      }
    };
    hook();
  });

  await page.goto('http://127.0.0.1:5000/', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForSelector('.leaflet-marker-icon', { timeout: 15000 });
  await page.waitForFunction(() => window.__map, { timeout: 10000 });

  const before = await page.evaluate(() => {
    const m = window.__map;
    return { zoom: m.getZoom(), lat: m.getCenter().lat, lon: m.getCenter().lng };
  });
  console.log('ANTES  zoom=' + before.zoom + ' center=[' + before.lat.toFixed(5) + ', ' + before.lon.toFixed(5) + ']');

  // Primer marcador = La Nubia (24)
  await page.locator('.leaflet-marker-icon').first().click();
  await page.waitForTimeout(2500); // deja terminar la animación

  const after = await page.evaluate(() => {
    const m = window.__map;
    const target = { lat: 5.029611, lon: -75.472041 };
    return {
      zoom: m.getZoom(), lat: m.getCenter().lat, lon: m.getCenter().lng,
      dLat: Math.abs(m.getCenter().lat - target.lat),
      dLon: Math.abs(m.getCenter().lng - target.lon),
      calls: window.__calls
    };
  });
  console.log('DESPUÉS zoom=' + after.zoom + ' center=[' + after.lat.toFixed(5) + ', ' + after.lon.toFixed(5) + ']');
  console.log('setView llamado con:', JSON.stringify(after.calls));
  console.log('distancia a La Nubia: dLat=' + after.dLat.toFixed(6) + ' dLon=' + after.dLon.toFixed(6));

  const ok = after.dLat < 0.003 && after.dLon < 0.003 && after.zoom >= 16;
  console.log(ok ? 'RESULTADO: OK el mapa se centró y hizo zoom a La Nubia' : 'RESULTADO: FALLÓ el zoom a La Nubia');

  if (logs.length) console.log('LOGS:', logs.join(' | '));
  await browser.close();
  process.exit(ok ? 0 : 1);
})();

