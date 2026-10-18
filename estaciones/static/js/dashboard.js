/* Dashboard de estaciones UNAL - sede Manizales.
 *
 * - Consulta la API cada cierto tiempo y actualiza las tarjetas.
 * - Dibuja la grafica de 24 h en canvas puro (sin librerias externas).
 * - Marca las estaciones en el mapa con Leaflet.
 *
 * Todo va en un archivo y sin framework: si el CDN de Leaflet falla, el
 * dashboard sigue funcionando (solo no se ve el mapa).
 */

const REFRESCO_MS = 60000;   // 1 minuto: holgado para datos cada 5 min
const URL_ULTIMA = '/api/v1/estaciones/ultima/';
const URL_SERIE = '/api/v1/estaciones/serie/';
const URL_PRONOSTICO = '/api/v1/estaciones/pronostico/';
const URL_HISTORIAL = '/api/v1/estaciones/historial/';

const ETIQUETAS = {
  temperatura: 'Temperatura (°C)',
  humedad_relativa: 'Humedad relativa (%)',
  precipitacion: 'Precipitación (mm)',
  presion_barometrica: 'Presión (hPa)',
  velocidad_viento: 'Viento (m/s)',
  radiacion_solar: 'Radiación solar (W/m²)'
};

/* Cada variable tiene su propio color, tipo de gráfico, icono y detalle.
   Así no se ven todas iguales como antes (todo azul). */
const ESTILOS_SERIE = {
  temperatura: {
    color: '#fb7185', colorSuave: 'rgba(251,113,133,0.28)',
    tipo: 'area', icono: '🌡️', unidad: '°C', dec: 1,
    detalle: 'Línea suavizada con relleno cálido + puntos máx/mín'
  },
  humedad_relativa: {
    color: '#38bdf8', colorSuave: 'rgba(56,189,248,0.25)',
    tipo: 'area', icono: '💧', unidad: '%', dec: 0,
    detalle: 'Área azul con curva suave'
  },
  precipitacion: {
    color: '#22d3ee', colorSuave: 'rgba(34,211,238,0.45)',
    tipo: 'barras', icono: '🌧️', unidad: 'mm', dec: 1,
    detalle: 'Barras de lluvia acumulada por intervalo'
  },
  presion_barometrica: {
    color: '#a78bfa', colorSuave: 'rgba(167,139,250,0.18)',
    tipo: 'linea', icono: '🧭', unidad: 'hPa', dec: 1,
    detalle: 'Línea fina violeta + promedio punteado'
  },
  radiacion_solar: {
    color: '#fbbf24', colorSuave: 'rgba(251,191,36,0.30)',
    tipo: 'picos', icono: '☀️', unidad: 'W/m²', dec: 0,
    detalle: 'Área dorada con base en cero y puntos de pico'
  }
};

function estiloDe(serie) {
  return ESTILOS_SERIE[serie] || {
    color: '#38bdf8', colorSuave: 'rgba(56,189,248,0.25)',
    tipo: 'area', icono: '📊', unidad: '', dec: 1, detalle: ''
  };
}

/* ---------- utilidades ---------- */

function formatear(valor, decimales) {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return '--';
  return Number(valor).toFixed(decimales);
}

function rosaDeLosVientos(grados) {
  if (grados === null || grados === undefined) return '';
  const nombres = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                   'S', 'SSO', 'SO', 'OSO', 'O', 'ONO', 'NO', 'NNO'];
  const idx = Math.round(((grados % 360) / 22.5)) % 16;
  return `(${nombres[idx]})`;
}

/* ---------- grafica en canvas ---------- */

function dibujarGrafica(lienzo, puntos, serie, etiqueta) {
  const ctx = lienzo.getContext('2d');
  const est = estiloDe(serie);   // color + tipo propio de cada variable
  const dpr = window.devicePixelRatio || 1;
  const ancho = lienzo.clientWidth;
  const alto = lienzo.clientHeight;

  // Ajusta el lienzo a la resolucion real de la pantalla.
  lienzo.width = Math.max(1, Math.floor(ancho * dpr));
  lienzo.height = Math.max(1, Math.floor(alto * dpr));
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, ancho, alto);

  const margen = { arriba: 18, derecha: 16, abajo: 34, izquierda: 56 };
  const w = ancho - margen.izquierda - margen.derecha;
  const h = alto - margen.arriba - margen.abajo;

  ctx.font = '11px "Segoe UI", sans-serif';

  if (!puntos.length) {
    ctx.fillStyle = '#94a3b8';
    ctx.textAlign = 'center';
    ctx.fillText('Sin datos en la ventana de 24 h', ancho / 2, alto / 2);
    return null;
  }

  // Los valores nulos (lectura sin ese dato) se ignoran para el escalado,
  // y se dibujan como hueco en la linea.
  const valores = puntos.map(p => p[serie]).filter(v => v !== null && v !== undefined);
  if (!valores.length) {
    ctx.fillStyle = '#94a3b8';
    ctx.textAlign = 'center';
    ctx.fillText('Sin datos de ' + etiqueta, ancho / 2, alto / 2);
    return null;
  }
  let vmin = Math.min(...valores);
  let vmax = Math.max(...valores);
  if (vmin === vmax) { vmin -= 1; vmax += 1; }
  // Radiación y lluvia nacen en cero para que los picos se aprecien.
  if (est.tipo === 'picos' || est.tipo === 'barras') vmin = Math.min(0, vmin);
  const pad = (vmax - vmin) * 0.12;
  vmin -= pad; vmax += pad;

  const tiempos = puntos.map(p => new Date(p.t).getTime());
  const tmin = Math.min(...tiempos);
  const tmax = Math.max(...tiempos);
  const rangoT = (tmax - tmin) || 1;

  const x = t => margen.izquierda + ((t - tmin) / rangoT) * w;
  const y = v => margen.arriba + (1 - (v - vmin) / (vmax - vmin)) * h;

  // Rejilla horizontal
  ctx.strokeStyle = '#334155';
  ctx.lineWidth = 1;
  ctx.fillStyle = '#94a3b8';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let i = 0; i <= 4; i++) {
    const valor = vmin + ((vmax - vmin) * i) / 4;
    const py = y(valor);
    ctx.globalAlpha = 0.35;
    ctx.beginPath();
    ctx.moveTo(margen.izquierda, py);
    ctx.lineTo(margen.izquierda + w, py);
    ctx.stroke();
    ctx.globalAlpha = 1;
    const decimales = Math.abs(vmax - vmin) < 5 ? 1 : 0;
    ctx.fillText(valor.toFixed(decimales), margen.izquierda - 8, py);
  }

  // Eje X: horas cada ~4 h
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  for (let i = 0; i <= 6; i++) {
    const t = tmin + (rangoT * i) / 6;
    const px = x(t);
    ctx.fillText(new Date(t).toLocaleTimeString('es-CO',
      { hour: '2-digit', minute: '2-digit' }), px, margen.arriba + h + 8);
  }

  // Relleno bajo la curva
  const trazo = puntos.filter(p => p[serie] !== null && p[serie] !== undefined);
  if (trazo.length > 1) {
    ctx.beginPath();
    ctx.moveTo(x(new Date(trazo[0].t).getTime()), y(trazo[0][serie]));
    for (const p of trazo.slice(1)) {
      ctx.lineTo(x(new Date(p.t).getTime()), y(p[serie]));
    }
    const grad = ctx.createLinearGradient(0, margen.arriba, 0, margen.arriba + h);
    grad.addColorStop(0, 'rgba(56, 189, 248, 0.30)');
    grad.addColorStop(1, 'rgba(56, 189, 248, 0.00)');
    ctx.lineTo(x(new Date(trazo[trazo.length - 1].t).getTime()), margen.arriba + h);
    ctx.lineTo(x(new Date(trazo[0].t).getTime()), margen.arriba + h);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();
  }

  // Linea
  ctx.beginPath();
  let primero = true;
  let anterior = null;
  for (const p of puntos) {
    const v = p[serie];
    const px = x(new Date(p.t).getTime());
    if (v === null || v === undefined) { primero = true; continue; }  // hueco
    if (primero) { ctx.moveTo(px, y(v)); primero = false; }
    else { ctx.lineTo(px, y(v)); }
    anterior = [px, y(v)];
  }
  ctx.strokeStyle = '#38bdf8';
  ctx.lineWidth = 2;
  ctx.lineJoin = 'round';
  ctx.stroke();

  // Punto del ultimo valor
  if (anterior) {
    ctx.beginPath();
    ctx.arc(anterior[0], anterior[1], 3.5, 0, Math.PI * 2);
    ctx.fillStyle = '#38bdf8';
    ctx.fill();
  }

  // Titulo con el color propio de cada variable.
  ctx.fillStyle = est.color;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  ctx.font = '600 12px "Segoe UI", sans-serif';
  ctx.fillText(`${est.icono}  ${etiqueta}`, margen.izquierda, 2);
  ctx.font = '11px "Segoe UI", sans-serif';

  // Curva suavizada (temperatura / humedad / radiacion).
  function trazarSuave(seg) {
    ctx.beginPath();
    seg.forEach((pt, i) => {
      const px = x(new Date(pt.t).getTime());
      const py = y(pt[serie]);
      if (i === 0) { ctx.moveTo(px, py); return; }
      const ant = seg[i - 1];
      const pax = x(new Date(ant.t).getTime());
      const pay = y(ant[serie]);
      const cx = (pax + px) / 2;
      ctx.bezierCurveTo(cx, pay, cx, py, px, py);
    });
  }

  // Linea recta (presion: se nota cada salto).
  function trazarRecto(seg) {
    ctx.beginPath();
    seg.forEach((pt, i) => {
      const px = x(new Date(pt.t).getTime());
      const py = y(pt[serie]);
      if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
    });
  }
}

/* ---------- mapa ---------- */

let mapa = null;


function iniciarMapa() {
  if (typeof L === 'undefined') return;      // el CDN de Leaflet no cargo

  // Caja de Manizales: impide alejar hasta el pais o mover el mapa fuera.
  const CAJA_MANIZALES = L.latLngBounds([4.98, -75.58], [5.10, -75.40]);
  mapa = L.map('mapa', {
    minZoom: 11,               // no se puede alejar mas alla de Manizales
    maxZoom: 19,               // acercamiento a nivel de calle/campus
    maxBounds: CAJA_MANIZALES, // rebota al intentar salir de la caja
    maxBoundsViscosity: 1.0,   // rebote firme, sin mostrar paises vecinos
  }).setView([5.0423, -75.4798], 12);   // entre La Nubia (SE) y Palogrande (N)

  // Capas base Esri (sin API key). Cada una declara su zoom nativo real:
  // mas alla de ese nivel Leaflet amplia el mosaico en vez de pedir uno
  // que no existe (eso era el gris "Map data not yet available").
  const ATRIB = 'Tiles &copy; Esri &mdash; Source: Esri, Maxar, ' +
    'Earthstar Geographics, and the GIS User Community';
  const satelite = L.layerGroup([
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/' +
      'World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 19, maxNativeZoom: 18, attribution: ATRIB
    }),
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/' +
      'Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 19, maxNativeZoom: 16
    })
  ]);
  const calles = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/' +
    'World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 19, maxNativeZoom: 18, attribution: ATRIB
  });
  const relieve = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/' +
    'World_Topo_Map/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 19, maxNativeZoom: 16, attribution: ATRIB
  });

  // Capa base por defecto: mapa de calles, claro y formal para ubicar
  // las estaciones (el tema oscuro se retiro del selector a proposito).
  calles.addTo(mapa);
  L.control.layers(
    { 'Calles': calles, 'Satelite': satelite, 'Relieve': relieve },
    null, { collapsed: false }
  ).addTo(mapa);

  const limites = [];
  document.querySelectorAll('.estacion-bloque').forEach(bloque => {
    const lat = parseFloat(bloque.dataset.lat);
    const lon = parseFloat(bloque.dataset.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;

    const marcador = L.marker([lat, lon]).addTo(mapa);
    marcador.bindPopup(
      `<strong>${bloque.dataset.nombre}</strong><br>` +
      `estacion ${bloque.dataset.estacion}<br>` +
      `<span id="popup-${bloque.dataset.estacion}">cargando...</span>`
    );
    marcador.on('popupopen', () => actualizarPopup(bloque.dataset.estacion));
    // Al hacer click en el marcador, centra el mapa en la estacion.
    // Zoom minimo 16: con 13 el viewport cabe mal contra la caja de Manizales
    // (maxBoundsViscosity recortaba la longitud de La Nubia) y ademas no se veia
    // un zoom claro. A 16 la vista entra sin recorte y se acerca a la estacion.
    marcador.on('click', () => {
      mapa.setView([lat, lon], Math.max(mapa.getZoom(), 16), { animate: true });
    });
    limites.push([lat, lon]);
  });

  if (limites.length > 1) {
    // El encuadre respeta el zoom minimo: si fitBounds quisiera alejar mas
    // alla de Manizales, el minZoom lo frena y maxBounds impide el arrastre.
    mapa.fitBounds(limites, { padding: [40, 40] });
  } else if (limites.length === 1) {
    mapa.setView(limites[0], 14);
  }
}

function actualizarPopup(codigo) {
  const el = document.getElementById(`popup-${codigo}`);
  if (!el) return;
  fetch(URL_ULTIMA)
    .then(r => r.json())
    .then(d => {
      const e = d.estaciones && d.estaciones[codigo];
      if (!e || !e.disponible) { el.textContent = 'sin datos'; return; }
      el.innerHTML = `${formatear(e.temperatura, 1)}&deg;C &middot; ` +
        `${formatear(e.humedad_relativa, 0)}% &middot; ` +
        `${formatear(e.presion_barometrica, 1)} hPa`;
    })
    .catch(() => { el.textContent = 'sin conexion'; });
}

/* ---------- actualizacion de las tarjetas ---------- */

function actualizarTarjetas(bloque, estacion) {
  bloque.querySelectorAll('.js-valor').forEach(el => {
    const valor = estacion[el.dataset.campo];
    const dec = parseInt(el.dataset.dec, 10) || 1;
    const unidad = el.querySelector('.unidad');
    el.textContent = (valor === null || valor === undefined)
      ? '--' : formatear(valor, dec);
    if (unidad) el.appendChild(unidad);      // se conserva la unidad
  });

  // Metricas derivadas del servidor (punto de rocio, tendencia, UV, ...).
  const der = estacion.derivados || {};
  bloque.querySelectorAll('.js-deriv').forEach(el => {
    const v = der[el.dataset.deriv];
    const dec = parseInt(el.dataset.dec, 10);
    const sufijo = el.dataset.sufijo || '';
    const unidad = el.querySelector('.unidad');
    if (v === null || v === undefined || v === '') {
      el.textContent = '--';
    } else if (Number.isFinite(Number(v)) && !Number.isNaN(dec)) {
      el.textContent = formatear(Number(v), dec);
    } else {
      el.textContent = String(v);            // textos: "En aumento", "Bajo", ...
    }
    if (unidad) el.appendChild(unidad);
    else if (sufijo) el.insertAdjacentText('beforeend', sufijo);
  });

  // Ultimo registro: "hace X min" (se recalcula en el servidor).
  const registro = bloque.querySelector('.js-registro');
  if (registro && der.hace) registro.textContent = 'Registro: ' + der.hace;

  // La aguja apunta hacia donde se dirige el viento.
  const aguja = bloque.querySelector('.js-aguja');
  if (aguja && Number.isFinite(estacion.direccion_viento)) {
    aguja.style.transform = `rotate(${estacion.direccion_viento + 180}deg)`;
  }

  const rosa = bloque.querySelector('.js-rosa');
  if (rosa) rosa.textContent = rosaDeLosVientos(estacion.direccion_viento);
}

async function cargarSerie(bloque, serie) {
  const codigo = bloque.dataset.estacion;
  const modo = bloque.dataset.modo === 'reciente' ? '&modo=reciente' : '';
  const lienzo = bloque.querySelector('.js-lienzo');
  const puntosEl = bloque.querySelector('.js-puntos');
  const actEl = bloque.querySelector('.js-actualizado');
  if (!lienzo) return;

  try {
    const r = await fetch(`${URL_SERIE}?estacion=${codigo}${modo}`);
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'error');

    dibujarGrafica(lienzo, d.datos, serie, ETIQUETAS[serie] || serie);

    // El titulo refleja la ventana real que devolvio el servidor.
    const titulo = bloque.querySelector('.js-titulo-grafica');
    if (titulo && d.ventana_desde && d.ventana_hasta) {
      const fmt = v => new Date(v).toLocaleString('es-CO',
        { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
      titulo.textContent =
        `Ventana ${fmt(d.ventana_desde)} - ${fmt(d.ventana_hasta)}`;
    }
    if (puntosEl) {
      puntosEl.textContent =
        `${d.puntos.toLocaleString('es-CO')} puntos` +
        ` (agrupados cada ${d.minutos_por_punto} min, de ` +
        `${d.lecturas_en_ventana.toLocaleString('es-CO')} lecturas)`;
    }
    if (actEl) actEl.textContent = 'actualizado ' +
      new Date().toLocaleTimeString('es-CO');
  } catch (err) {
    dibujarGrafica(lienzo, [], serie, ETIQUETAS[serie] || serie);
    if (puntosEl) puntosEl.textContent = 'no se pudo cargar la serie';
  }
}

/* ---------- pronostico y visibilidad (Open-Meteo) ---------- */

async function cargarPronostico(bloque) {
  const visEl = bloque.querySelector('.js-pro-vis');
  if (!visEl) return;                       // panel sin tarjetas nuevas
  const unidadVis = visEl.querySelector('.unidad');
  const cat = bloque.querySelector('.js-pro-vis-cat');
  const ico = bloque.querySelector('.js-pro-icono');
  const txt = bloque.querySelector('.js-pro-texto');
  const horas = bloque.querySelector('.js-pro-horas');

  try {
    const r = await fetch(`${URL_PRONOSTICO}?estacion=${bloque.dataset.estacion}`);
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'error');

    const km = d.actual && d.actual.visibilidad_km;
    visEl.textContent = (km === null || km === undefined)
      ? '--' : formatear(km, km < 10 ? 1 : 0);
    if (unidadVis) visEl.appendChild(unidadVis);
    if (cat) cat.textContent =
      (d.actual && d.actual.visibilidad_categoria) || '--';

    if (ico) ico.textContent = (d.actual && d.actual.emoji) || '❔';
    if (txt) txt.textContent = (d.actual && d.actual.texto) || '--';

    if (horas) {
      horas.innerHTML = (d.horas || []).map(h =>
        `<span class="pro-hora" title="${h.texto}">` +
        `${h.hora} ${h.emoji} ${formatear(h.temperatura, 0)}&deg; ` +
        `💧${h.prob_lluvia === null ? '--' : h.prob_lluvia}%</span>`
      ).join('') || 'sin pronostico';
    }
  } catch (err) {
    visEl.textContent = '--';
    if (unidadVis) visEl.appendChild(unidadVis);
    if (cat) cat.textContent = 'modelo no disponible';
    if (txt) txt.textContent = 'sin conexion';
    if (horas) horas.textContent = 'Open-Meteo no respondio';
  }
}

async function refrescar() {
  const punto = document.getElementById('punto-estado');
  const texto = document.getElementById('texto-estado');
  try {
    const r = await fetch(URL_ULTIMA);
    if (!r.ok) throw new Error('http ' + r.status);
    const d = await r.json();
    document.querySelectorAll('.estacion-bloque').forEach(bloque => {
      const est = d.estaciones && d.estaciones[bloque.dataset.estacion];
      if (est && est.disponible) actualizarTarjetas(bloque, est);
      cargarPronostico(bloque);   // visibilidad y pronostico (Open-Meteo)
    });
    if (punto) punto.className = 'punto vivo';
    if (texto) texto.textContent = 'en linea';
  } catch (err) {
    if (punto) punto.className = 'punto muerto';
    if (texto) texto.textContent = 'sin conexion con el servidor';
  }
}

/* ---------- fondo rotativo de los campus ---------- */

// Fotos libres (Wikimedia Commons, CC) de la UNAL sede Manizales, con su
// pagina de creditos. Copias locales en static/img (se pre-cargan arriba).
const FOTOS_FONDO = [
  { titulo: 'Campus La Nubia', src: '/static/img/nubia.png', pagina: 'https://commons.wikimedia.org/wiki/File:UNAL-Campus_La_Nubia-Manizales.png' },
  { titulo: 'Campus Palogrande', src: '/static/img/palogrande.png', pagina: 'https://commons.wikimedia.org/wiki/File:UNAL-Campus_Palogrande-Manizales.png' },
  { titulo: 'Campus El Cable', src: '/static/img/cable.png', pagina: 'https://commons.wikimedia.org/wiki/File:UNAL-Campus_El_Cable-Manizales.png' },
  { titulo: 'UNAL Manizales', src: '/static/img/mzl.jpg', pagina: 'https://commons.wikimedia.org/wiki/File:UNAL_MZL.JPG' },
  { titulo: 'Biblioteca UNAL Manizales', src: '/static/img/biblio.jpg', pagina: 'https://commons.wikimedia.org/wiki/File:Biblio_unal.JPG' },
  { titulo: 'Palogrande UNAL', src: '/static/img/palogrande2.jpg', pagina: 'https://commons.wikimedia.org/wiki/File:Unal_Manizales_-_Palogrande.jpg' },
];
const FONDO_MS = 12000;    // cada foto visible 12 s
let fondoIndice = 0;
let fondoPar = false;

function mostrarFoto(i) {
  const foto = FOTOS_FONDO[i % FOTOS_FONDO.length];
  const capaNueva = document.getElementById(fondoPar ? 'fondo-b' : 'fondo-a');
  const capaVieja = document.getElementById(fondoPar ? 'fondo-a' : 'fondo-b');
  if (!capaNueva || !capaVieja) return;
  const img = new Image();
  img.onload = () => {
    capaNueva.style.backgroundImage = `url("${foto.src}")`;
    capaNueva.classList.add('visible');
    capaVieja.classList.remove('visible');
    fondoPar = !fondoPar;
    const credito = document.getElementById('fondo-credito');
    if (credito) {
      credito.textContent = `Foto: ${foto.titulo} - Wikimedia Commons`;
      credito.href = foto.pagina;
    }
  };
  img.onerror = () => { fondoIndice++; };   // si falla una foto, se salta
  img.src = foto.src;
}

function iniciarFondo() {
  if (!FOTOS_FONDO.length) return;
  mostrarFoto(fondoIndice);
  setInterval(() => { fondoIndice++; mostrarFoto(fondoIndice); }, FONDO_MS);
}

/* ---------- pestanas por estacion ---------- */

function mostrarEstacion(codigo) {
  document.querySelectorAll('.estacion-bloque').forEach(bloque => {
    const activo = bloque.dataset.panel === String(codigo);
    bloque.classList.toggle('oculto', !activo);
    if (activo) {
      // La grafica de un panel oculto tiene ancho 0: al mostrarlo se
      // redibuja la serie activa con las medidas reales.
      const boton = bloque.querySelector('.js-selector button.activo');
      cargarSerie(bloque, boton ? boton.dataset.serie : 'temperatura');
      if (bloque._hist) renderGraficaHistorial(bloque);
    }
  });
  document.querySelectorAll('.pestana').forEach(p => {
    const activa = p.dataset.pestana === String(codigo);
    p.classList.toggle('activa', activa);
    p.setAttribute('aria-selected', activa ? 'true' : 'false');
  });
  centrarMapaEn(codigo);
}

function centrarMapaEn(codigo) {
  if (!mapa || typeof L === 'undefined') return;
  const bloque = document.querySelector(`.estacion-bloque[data-panel="${codigo}"]`);
  if (!bloque) return;
  const lat = parseFloat(bloque.dataset.lat);
  const lon = parseFloat(bloque.dataset.lon);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
  mapa.setView([lat, lon], Math.max(mapa.getZoom(), 16), { animate: true });
  mapa.invalidateSize();   // el mapa pudo cambiar de tamano con las pestanas
}

/* ---------- historial y estadisticas (drill-down ano/mes/dia/hora) ---------- */

const MESES_HIST = ['ene', 'feb', 'mar', 'abr', 'may', 'jun',
  'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

// Columnas de la tabla de estadisticas: k = campo, t = titulo, cls = color.
const COLS_HIST = [
  { k: 'etiqueta', t: 'Periodo' },
  { k: 'n', t: 'Lect.', dec: 0 },
  { k: 't_min', t: 'T m&iacute;n', dec: 1, cls: 'c-frio' },
  { k: 't_max', t: 'T m&aacute;x', dec: 1, cls: 'c-calor' },
  { k: 't_avg', t: 'T prom', dec: 1 },
  { k: 'lluvia', t: 'Lluvia mm', dec: 1 },
  { k: 'v_avg', t: 'V prom', dec: 1 },
  { k: 'v_max', t: 'V m&aacute;x', dec: 1 },
  { k: 'h_avg', t: 'H prom', dec: 0 },
  { k: 'p_avg', t: 'P prom', dec: 1 },
  { k: 'r_avg', t: 'R prom', dec: 0 },
  { k: 'r_max', t: 'R m&aacute;x', dec: 0 },
];

// Columnas de la tabla de datos crudos (una lectura cada 5 min).
const COLS_CRUDOS = [
  { k: 't', t: 'Hora' },
  { k: 'temperatura', t: 'T &deg;C', dec: 1 },
  { k: 'humedad_relativa', t: 'H %', dec: 0 },
  { k: 'precipitacion', t: 'Lluvia mm', dec: 1 },
  { k: 'presion_barometrica', t: 'P hPa', dec: 1 },
  { k: 'velocidad_viento', t: 'V m/s', dec: 1 },
  { k: 'direccion_viento', t: 'Dir &deg;', dec: 0 },
  { k: 'radiacion_solar', t: 'R W/m&sup2;', dec: 0 },
];

function initHistorial(bloque) {
  const selAnio = bloque.querySelector('.js-hist-anio');
  const selMes = bloque.querySelector('.js-hist-mes');
  const selDia = bloque.querySelector('.js-hist-dia');
  const btnCrudos = bloque.querySelector('.js-hist-crudos');
  const btnCsv = bloque.querySelector('.js-hist-csv');
  if (!selAnio) return;                       // bloque sin datos

  // Estado del drill-down de este bloque.
  bloque._hist = { anio: '', mes: '', dia: '', crudos: false,
                   var: 'temperatura', filas: [], resumen: {} };

  // Selector de variable de la grafica del historial.
  const selHist = bloque.querySelector('.js-hist-selector');
  if (selHist) {
    selHist.querySelectorAll('button').forEach(btn => {
      btn.addEventListener('click', () => {
        selHist.querySelectorAll('button').forEach(b =>
          b.classList.remove('activo'));
        btn.classList.add('activo');
        bloque._hist.var = btn.dataset.var;
        renderGraficaHistorial(bloque);      // solo redibuja, no refresca
      });
    });
  }

  selAnio.addEventListener('change', () => {
    bloque._hist.anio = selAnio.value;
    bloque._hist.mes = bloque._hist.dia = '';
    cargarHistorial(bloque);
  });
  selMes.addEventListener('change', () => {
    bloque._hist.mes = selMes.value;
    bloque._hist.dia = '';
    cargarHistorial(bloque);
  });
  selDia.addEventListener('change', () => {
    bloque._hist.dia = selDia.value;
    cargarHistorial(bloque);
  });
  btnCrudos.addEventListener('click', () => {
    bloque._hist.crudos = !bloque._hist.crudos;
    cargarHistorial(bloque);
  });
  btnCsv.addEventListener('click', () => exportarHistorialCsv(bloque));

  cargarHistorial(bloque);                     // primer nivel: anios
}

async function cargarHistorial(bloque) {
  const h = bloque._hist;
  const tabla = bloque.querySelector('.js-hist-tabla');
  const migas = bloque.querySelector('.js-hist-migas');
  if (!tabla) return;

  const params = new URLSearchParams({ estacion: bloque.dataset.estacion });
  if (h.anio) params.set('anio', h.anio);
  if (h.anio && h.mes) params.set('mes', h.mes);
  if (h.anio && h.mes && h.dia) params.set('dia', h.dia);
  if (h.crudos) params.set('crudos', '1');

  tabla.innerHTML = '<p class="historial-cargando">cargando&hellip;</p>';
  try {
    const r = await fetch(`${URL_HISTORIAL}?${params}`);
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'error');
    h.nivel = d.nivel;
    h.filas = d.filas;
    h.resumen = d.resumen || {};

    renderMigasHistorial(bloque, d);
    renderResumenHistorial(bloque, h.resumen);
    renderTablaHistorial(bloque, d);
    poblarSelectoresHistorial(bloque, d);
    renderGraficaHistorial(bloque);
  } catch (err) {
    tabla.innerHTML =
      '<p class="historial-cargando">no se pudo cargar el historial</p>';
    if (migas) migas.innerHTML = '';
  }
}

function renderMigasHistorial(bloque, d) {
  const migas = bloque.querySelector('.js-hist-migas');
  if (!migas) return;
  const h = bloque._hist;
  const partes = [];
  partes.push('<button type="button" class="historial-miga" data-nivel="anios">A&ntilde;os</button>');
  if (d.nivel !== 'anio') {
    partes.push(`<button type="button" class="historial-miga" data-nivel="anio">${h.anio}</button>`);
  }
  if (d.nivel === 'dia' || d.nivel === 'hora' || d.nivel === 'crudos') {
    partes.push(`<button type="button" class="historial-miga" data-nivel="mes">${MESES_HIST[h.mes - 1]}</button>`);
  }
  if (d.nivel === 'hora' || d.nivel === 'crudos') {
    partes.push(`<button type="button" class="historial-miga activa">${h.dia}</button>`);
  }
  migas.innerHTML = partes.join('<span class="historial-miga-sep">&rsaquo;</span>');
  migas.querySelectorAll('.historial-miga').forEach(btn => {
    btn.addEventListener('click', () => {
      const h2 = bloque._hist;
      if (btn.dataset.nivel === 'anios') {
        h2.anio = h2.mes = h2.dia = '';
      } else if (btn.dataset.nivel === 'anio') {
        h2.mes = h2.dia = '';
      } else if (btn.dataset.nivel === 'mes') {
        h2.dia = '';
      }
      h2.crudos = false;
      cargarHistorial(bloque);
    });
  });
}

function renderResumenHistorial(bloque, r) {
  const el = bloque.querySelector('.js-hist-resumen');
  if (!el || !r) return;
  const chips = [
    { t: 'Lecturas', v: r.n != null ? Number(r.n).toLocaleString('es-CO') : '--' },
    { t: 'T m&iacute;n', v: formatear(r.t_min, 1), cls: 'c-frio' },
    { t: 'T m&aacute;x', v: formatear(r.t_max, 1), cls: 'c-calor' },
    { t: 'Lluvia', v: formatear(r.lluvia, 1), suf: ' mm' },
    { t: 'V m&aacute;x', v: formatear(r.v_max, 1), suf: ' m/s' },
    { t: 'H prom', v: formatear(r.h_avg, 0), suf: ' %' },
  ];
  el.innerHTML = chips.map(c =>
    `<span class="hist-chip ${c.cls || ''}">${c.t}: ` +
    `<strong>${c.v}${c.suf || ''}</strong></span>`).join('');
}

function renderTablaHistorial(bloque, d) {
  const el = bloque.querySelector('.js-hist-tabla');
  if (!el) return;

  const cols = d.nivel === 'crudos' ? COLS_CRUDOS : COLS_HIST;
  const encabezado = cols.map(c =>
    `<th${c.cls ? ` class="${c.cls}"` : ''}>${c.t}</th>`).join('');
  const cuerpo = d.filas.map(fila => {
    const celdas = cols.map(c => {
      if (c.k === 't') {
        return `<td class="c-hora">${(fila[c.k] || '').slice(11, 16) || '--'}</td>`;
      }
      if (c.k === 'etiqueta') {
        return `<td class="c-hora">${fila[c.k]}</td>`;
      }
      const v = fila[c.k];
      return `<td${c.cls ? ` class="${c.cls}"` : ''}>` +
        `${formatear(v, c.dec !== undefined ? c.dec : 1)}</td>`;
    }).join('');
    return `<tr>${celdas}</tr>`;
  }).join('');

  el.innerHTML = d.filas.length
    ? `<table class="historial-tabla"><thead><tr>${encabezado}</tr></thead>` +
      `<tbody>${cuerpo}</tbody></table>`
    : '<p class="historial-cargando">sin lecturas en este per&iacute;odo</p>';
}

function poblarSelectoresHistorial(bloque, d) {
  const selAnio = bloque.querySelector('.js-hist-anio');
  const selMes = bloque.querySelector('.js-hist-mes');
  const selDia = bloque.querySelector('.js-hist-dia');
  const btnCrudos = bloque.querySelector('.js-hist-crudos');
  const h = bloque._hist;
  if (!selAnio) return;

  // Anios disponibles: siempre desde el nivel base (la primera carga).
  if (d.nivel === 'anio') {
    h.anios = d.filas.map(f => f.anio);
    selAnio.innerHTML = '<option value="">A&ntilde;o</option>' +
      h.anios.map(a => `<option value="${a}"${a == h.anio ? ' selected' : ''}>${a}</option>`).join('');
  } else {
    selAnio.value = h.anio;
  }

  // Meses con datos del ano elegido (llegan en el nivel 'mes').
  if (d.nivel === 'mes') {
    selMes.disabled = false;
    selMes.innerHTML = '<option value="">Mes</option>' +
      d.filas.map(f =>
        `<option value="${f.mes}"${f.mes == h.mes ? ' selected' : ''}>` +
        `${MESES_HIST[f.mes - 1]}</option>`).join('');
  } else if (d.nivel === 'anio') {
    selMes.disabled = true;
    selMes.innerHTML = '<option value="">Mes</option>';
  }

  // Dias con datos del mes elegido (llegan en el nivel 'dia').
  if (d.nivel === 'dia') {
    selDia.disabled = false;
    selDia.innerHTML = '<option value="">D&iacute;a</option>' +
      d.filas.map(f =>
        `<option value="${f.dia}"${f.dia == h.dia ? ' selected' : ''}>` +
        `${f.dia}</option>`).join('');
  } else if (d.nivel !== 'hora' && d.nivel !== 'crudos') {
    selDia.disabled = true;
    selDia.innerHTML = '<option value="">D&iacute;a</option>';
  }

  if (btnCrudos) {
    btnCrudos.disabled = !(h.anio && h.mes && h.dia);
    btnCrudos.textContent = h.crudos ? 'Por hora' : 'Datos crudos';
    if (h.crudos) btnCrudos.title = 'Vuelve a las estadisticas por hora';
    else btnCrudos.title = 'Lecturas de 5 min de ese dia';
  }
}

function exportarHistorialCsv(bloque) {
  const h = bloque._hist;
  if (!h.filas || !h.filas.length) return;
  const cols = h.nivel === 'crudos' ? COLS_CRUDOS : COLS_HIST;
  // Separador ';' y BOM: Excel en es-CO lo abre bien con doble clic.
  const lineas = [cols.map(c => c.t.replace(/&[^;]+;/g, '')).join(';')];
  for (const f of h.filas) {
    lineas.push(cols.map(c => f[c.k] !== null && f[c.k] !== undefined
      ? f[c.k] : '').join(';'));
  }
  const blob = new Blob(['\uFEFF' + lineas.join('\r\n')],
    { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  const est = bloque.dataset.estacion;
  const nombre = h.nivel === 'crudos'
    ? `estacion-${est}-crudos-${h.anio}-${h.mes}-${h.dia}.csv`
    : `estacion-${est}-historial-${h.nivel}.csv`;
  a.href = URL.createObjectURL(blob);
  a.download = nombre;
  a.click();
  URL.revokeObjectURL(a.href);
}

/* ---------- grafica del historial (canvas puro, como la de 24 h) ---------- */

// Como se dibuja cada variable segun el nivel agregado:
//   banda   : temperatura, area entre t_min y t_max + linea de t_avg
//   barras  : lluvia acumulada por cubo
//   linea   : promedio simple con relleno
//   linea2  : promedio solido + maximo punteado
const ESTILOS_HIST = {
  temperatura: {
    titulo: 'Temperatura (\u00b0C)', color: '#fb7185', tipo: 'banda',
    campos: ['t_min', 't_avg', 't_max'],
    leyenda: [['promedio', '#fb7185'],
              ['rango m\u00edn\u2013m\u00e1x', 'rgba(251,113,133,0.20)']],
  },
  lluvia: {
    titulo: 'Lluvia (mm)', color: '#22d3ee', tipo: 'barras',
    campos: ['lluvia'],
    leyenda: [['total del per\u00edodo', 'rgba(34,211,238,0.55)']],
  },
  humedad: {
    titulo: 'Humedad promedio (%)', color: '#38bdf8', tipo: 'linea',
    campos: ['h_avg'], leyenda: [['promedio', '#38bdf8']],
  },
  presion: {
    titulo: 'Presi\u00f3n promedio (hPa)', color: '#a78bfa', tipo: 'linea',
    campos: ['p_avg'], leyenda: [['promedio', '#a78bfa']],
  },
  viento: {
    titulo: 'Viento (m/s)', color: '#5eead4', tipo: 'linea2',
    campos: ['v_avg', 'v_max'],
    leyenda: [['promedio', '#5eead4'], ['m\u00e1ximo', '#8fa3bf']],
  },
  radiacion: {
    titulo: 'Radiaci\u00f3n (W/m\u00b2)', color: '#fbbf24', tipo: 'linea2',
    campos: ['r_avg', 'r_max'],
    leyenda: [['promedio', '#fbbf24'], ['m\u00e1ximo', '#8fa3bf']],
  },
};

// En el nivel de datos crudos cada variable es su campo de 5 min.
const CAMPOS_HIST_CRUDOS = {
  temperatura: 'temperatura', lluvia: 'precipitacion',
  humedad: 'humedad_relativa', presion: 'presion_barometrica',
  viento: 'velocidad_viento', radiacion: 'radiacion_solar',
};

function descripcionPeriodoHistorial(h) {
  if (h.nivel === 'anio') return 'por a\u00f1o';
  if (h.nivel === 'mes') return `${h.anio} por mes`;
  if (h.nivel === 'dia') return `${MESES_HIST[h.mes - 1]} ${h.anio} por d\u00eda`;
  if (h.nivel === 'hora') return `${h.dia} ${MESES_HIST[h.mes - 1]} ${h.anio} por hora`;
  return `${h.dia} ${MESES_HIST[h.mes - 1]} ${h.anio} \u00b7 datos de 5 min`;
}

function renderGraficaHistorial(bloque) {
  const h = bloque._hist;
  const lienzo = bloque.querySelector('.js-hist-lienzo');
  if (!lienzo || !h) return;
  const titulo = bloque.querySelector('.js-hist-titulo-grafica');
  const leyenda = bloque.querySelector('.js-hist-leyenda');
  const estilo = ESTILOS_HIST[h.var] || ESTILOS_HIST.temperatura;

  let etiquetas, series;
  if (h.nivel === 'crudos') {
    const campo = CAMPOS_HIST_CRUDOS[h.var];
    etiquetas = h.filas.map(f => (f.t || '').slice(11, 16));
    series = [h.filas.map(f => f[campo])];
  } else {
    // Etiquetas cortas por nivel: "2004" | "sep" | "15" | "14:00".
    etiquetas = h.filas.map(f =>
      h.nivel === 'anio' ? String(f.anio) :
      h.nivel === 'mes' ? MESES_HIST[f.mes - 1] :
      h.nivel === 'dia' ? String(f.dia) : f.hora);
    series = estilo.campos.map(c => h.filas.map(f => f[c]));
  }

  if (titulo) {
    titulo.innerHTML = `${estilo.titulo} &mdash; ${bloque.dataset.nombre}, ` +
      descripcionPeriodoHistorial(h);
  }
  if (leyenda) {
    leyenda.innerHTML = (estilo.leyenda || []).map(([txt, col]) =>
      `<span class="hist-leyenda-item"><i style="background:${col}"></i>${txt}</span>`
    ).join('');
  }
  dibujarGraficaHistorial(lienzo, etiquetas, series, estilo);
}

function trazarLineaHistorial(ctx, x, y, valores, n, color, ancho, punteada) {
  ctx.save();
  if (punteada) ctx.setLineDash([4, 4]);
  ctx.beginPath();
  let primero = true;
  for (let i = 0; i < n; i++) {
    const v = valores[i];
    if (v === null || v === undefined) { primero = true; continue; }  // hueco
    if (primero) { ctx.moveTo(x(i), y(v)); primero = false; }
    else { ctx.lineTo(x(i), y(v)); }
  }
  ctx.strokeStyle = color;
  ctx.lineWidth = ancho;
  ctx.lineJoin = 'round';
  ctx.stroke();
  ctx.restore();
}

function dibujarGraficaHistorial(lienzo, etiquetas, series, estilo) {
  const ctx = lienzo.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const ancho = lienzo.clientWidth;
  const alto = lienzo.clientHeight;
  lienzo.width = Math.max(1, Math.floor(ancho * dpr));
  lienzo.height = Math.max(1, Math.floor(alto * dpr));
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, ancho, alto);
  if (ancho === 0 || alto === 0) return;       // panel oculto

  ctx.font = '11px "Segoe UI", sans-serif';
  const n = etiquetas.length;
  const margen = { arriba: 16, derecha: 14, abajo: 34, izquierda: 56 };
  const w = ancho - margen.izquierda - margen.derecha;
  const h = alto - margen.arriba - margen.abajo;

  const sinDatos = texto => {
    ctx.fillStyle = '#8fa3bf';
    ctx.textAlign = 'center';
    ctx.fillText(texto, ancho / 2, alto / 2);
  };
  if (!n) { sinDatos('sin lecturas en este per\u00edodo'); return; }

  const presentes = series.flat().filter(v => v !== null && v !== undefined);
  if (!presentes.length) { sinDatos('sin datos de ' + estilo.titulo); return; }

  let vmin = Math.min(...presentes);
  let vmax = Math.max(...presentes);
  if (estilo.tipo === 'barras') vmin = Math.min(0, vmin);   // barras nacen en 0
  if (vmin === vmax) { vmin -= 1; vmax += 1; }
  const pad = (vmax - vmin) * 0.1;
  vmin -= pad; vmax += pad;

  const x = i => margen.izquierda + (n === 1 ? w / 2 : (i / (n - 1)) * w);
  const y = v => margen.arriba + (1 - (v - vmin) / (vmax - vmin)) * h;

  // Rejilla horizontal + eje Y (igual que la grafica de 24 h)
  ctx.strokeStyle = '#22344f';
  ctx.lineWidth = 1;
  ctx.fillStyle = '#8fa3bf';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let i = 0; i <= 4; i++) {
    const valor = vmin + ((vmax - vmin) * i) / 4;
    const py = y(valor);
    ctx.globalAlpha = 0.5;
    ctx.beginPath();
    ctx.moveTo(margen.izquierda, py);
    ctx.lineTo(margen.izquierda + w, py);
    ctx.stroke();
    ctx.globalAlpha = 1;
    const dec = Math.abs(vmax - vmin) < 5 ? 1 : 0;
    ctx.fillText(valor.toFixed(dec), margen.izquierda - 8, py);
  }

  // Eje X: etiquetas adelgazadas a ~14 visibles
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  const paso = Math.max(1, Math.ceil(n / 14));
  for (let i = 0; i < n; i += paso) {
    ctx.fillText(etiquetas[i], x(i), margen.arriba + h + 8);
  }

  if (estilo.tipo === 'barras') {
    const anchoBarra = Math.max(2, (w / n) * 0.72);
    const y0 = Math.max(margen.arriba, Math.min(margen.arriba + h, y(0)));
    for (let i = 0; i < n; i++) {
      const v = series[0][i];
      if (v === null || v === undefined) continue;
      const py = y(v);
      ctx.fillStyle = 'rgba(34, 211, 238, 0.55)';
      ctx.fillRect(x(i) - anchoBarra / 2, Math.min(py, y0),
        anchoBarra, Math.abs(y0 - py));
    }
    return;
  }

  if (estilo.tipo === 'banda' && series.length === 3) {
    const [mins, , maxs] = series;
    // Banda min-max: recorre el maximo hacia adelante y el minimo hacia atras.
    ctx.beginPath();
    let started = false;
    for (let i = 0; i < n; i++) {
      const v = maxs[i];
      if (v === null || v === undefined) continue;
      if (!started) { ctx.moveTo(x(i), y(v)); started = true; }
      else ctx.lineTo(x(i), y(v));
    }
    if (!started) { sinDatos('sin datos de ' + estilo.titulo); return; }
    for (let i = n - 1; i >= 0; i--) {
      const v = mins[i];
      if (v === null || v === undefined) continue;
      ctx.lineTo(x(i), y(v));
    }
    ctx.closePath();
    ctx.fillStyle = 'rgba(251, 113, 133, 0.16)';
    ctx.fill();
    trazarLineaHistorial(ctx, x, y, series[1], n, estilo.color, 2, false);
    return;
  }

  if (estilo.tipo === 'linea2') {
    trazarLineaHistorial(ctx, x, y, series[1], n, '#8fa3bf', 1.5, true);
    trazarLineaHistorial(ctx, x, y, series[0], n, estilo.color, 2, false);
    return;
  }

  // linea simple con relleno bajo la curva
  const vals = series[0];
  let firstX = null, lastX = null;
  ctx.beginPath();
  let primero = true;
  for (let i = 0; i < n; i++) {
    const v = vals[i];
    if (v === null || v === undefined) continue;
    const px = x(i), py = y(v);
    if (firstX === null) firstX = px;
    lastX = px;
    if (primero) { ctx.moveTo(px, py); primero = false; }
    else ctx.lineTo(px, py);
  }
  if (firstX === null) { sinDatos('sin datos de ' + estilo.titulo); return; }
  ctx.lineTo(lastX, margen.arriba + h);
  ctx.lineTo(firstX, margen.arriba + h);
  ctx.closePath();
  const grad = ctx.createLinearGradient(0, margen.arriba, 0, margen.arriba + h);
  grad.addColorStop(0, estilo.color + '44');       // hex + alpha
  grad.addColorStop(1, estilo.color + '00');
  ctx.fillStyle = grad;
  ctx.fill();
  trazarLineaHistorial(ctx, x, y, vals, n, estilo.color, 2, false);
}

/* ---------- arranque ---------- */

document.addEventListener('DOMContentLoaded', () => {
  iniciarFondo();
  iniciarMapa();

  document.querySelectorAll('.pestana').forEach(p => {
    p.addEventListener('click', () => mostrarEstacion(p.dataset.pestana));
  });

  // Pronostico (Open-Meteo): independiente de la API propia: si el servidor
  // local esta caido pero hay internet, estas tarjetas aun se llenan.
  document.querySelectorAll('.estacion-bloque').forEach(cargarPronostico);

  // Menu lateral: desplazamiento suave a cada seccion del panel visible.
  document.querySelectorAll('.menu-item').forEach(item => {
    item.addEventListener('click', () => {
      document.querySelectorAll('.menu-item').forEach(m => m.classList.remove('activo'));
      item.classList.add('activo');
      const destino = item.dataset.ir;
      const panel = document.querySelector('.estacion-bloque:not(.oculto)') || document;
      const mapa = {
        arriba: () => document.getElementById('arriba'),
        metricas: () => panel.querySelector('.zona-metricas'),
        grafica: () => panel.querySelector('.zona-grafica'),
        historial: () => panel.querySelector('.zona-historial'),
        mapa: () => document.getElementById('mapa-seccion'),
        pie: () => document.getElementById('pie'),
      }[destino];
      const el = mapa ? mapa() : null;
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });

  document.querySelectorAll('.estacion-bloque').forEach(bloque => {
    cargarSerie(bloque, 'temperatura');
    initHistorial(bloque);
    bloque.querySelectorAll('.js-selector button').forEach(boton => {
      boton.addEventListener('click', () => {
        bloque.querySelectorAll('.js-selector button').forEach(b =>
          b.classList.remove('activo'));
        boton.classList.add('activo');
        cargarSerie(bloque, boton.dataset.serie);
      });
    });
  });

  refrescar();
  setInterval(refrescar, REFRESCO_MS);

  // Al cambiar el tamano de la ventana se redibuja con las nuevas medidas.
  let temporizador = null;
  window.addEventListener('resize', () => {
    clearTimeout(temporizador);
    temporizador = setTimeout(() => {
      document.querySelectorAll('.estacion-bloque').forEach(bloque => {
        const activo = bloque.querySelector('.js-selector button.activo');
        cargarSerie(bloque, activo ? activo.dataset.serie : 'temperatura');
        if (bloque._hist) renderGraficaHistorial(bloque);
      });
    }, 200);
  });
});

/* OVERRIDE: cada variable con su color y tipo de grafico propio. */
function trazarSuave2(ctx, X, Y, seg, serie) {
  ctx.beginPath();
  seg.forEach((pt, i) => {
    const px = X(new Date(pt.t).getTime());
    const py = Y(pt[serie]);
    if (i === 0) { ctx.moveTo(px, py); return; }
    const ant = seg[i - 1];
    const pax = X(new Date(ant.t).getTime());
    const pay = Y(ant[serie]);
    const cx = (pax + px) / 2;
    ctx.bezierCurveTo(cx, pay, cx, py, px, py);
  });
}

function trazarRecto2(ctx, X, Y, seg, serie) {
  ctx.beginPath();
  seg.forEach((pt, i) => {
    const px = X(new Date(pt.t).getTime());
    const py = Y(pt[serie]);
    if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
  });
}

function dibujarGrafica(lienzo, puntos, serie, etiqueta) {
  const est = estiloDe(serie);
  const ctx = lienzo.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const ancho = lienzo.clientWidth;
  const alto = lienzo.clientHeight;
  lienzo.width = Math.max(1, Math.floor(ancho * dpr));
  lienzo.height = Math.max(1, Math.floor(alto * dpr));
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, ancho, alto);
  const margen = { arriba: 20, derecha: 16, abajo: 34, izquierda: 56 };
  const w = ancho - margen.izquierda - margen.derecha;
  const h = alto - margen.arriba - margen.abajo;
  ctx.font = '11px "Segoe UI", sans-serif';
  const vals = puntos.map(p => p[serie]).filter(v => v !== null && v !== undefined);
  if (!puntos.length || !vals.length) {
    ctx.fillStyle = '#94a3b8';
    ctx.textAlign = 'center';
    ctx.fillText('Sin datos', ancho / 2, alto / 2);
    lienzo._stats = null;
    return null;
  }
  let vmin = Math.min.apply(null, vals);
  let vmax = Math.max.apply(null, vals);
  if (vmin === vmax) { vmin -= 1; vmax += 1; }
  const esBarras = est.tipo === 'barras';
  const esPicos = est.tipo === 'picos';
  if (esBarras || esPicos) vmin = Math.min(0, vmin);
  const pad2 = (vmax - vmin) * 0.12;
  vmin -= pad2; vmax += pad2;
  lienzo._vminG = vmin;
  const tiempos = puntos.map(p => new Date(p.t).getTime());
  const tmin = Math.min.apply(null, tiempos);
  const tmax = Math.max.apply(null, tiempos);
  const rangoT = (tmax - tmin) || 1;
  const X = t => margen.izquierda + ((t - tmin) / rangoT) * w;
  const Y = v => margen.arriba + (1 - (v - vmin) / (vmax - vmin)) * h;
  ctx.strokeStyle = '#334155';
  ctx.lineWidth = 1;
  ctx.fillStyle = '#94a3b8';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let i = 0; i <= 4; i++) {
    const vv = vmin + ((vmax - vmin) * i) / 4;
    const py = Y(vv);
    ctx.globalAlpha = 0.35;
    ctx.beginPath();
    ctx.moveTo(margen.izquierda, py);
    ctx.lineTo(margen.izquierda + w, py);
    ctx.stroke();
    ctx.globalAlpha = 1;
    ctx.fillText(formatear(vv, 1), margen.izquierda - 8, py);
  }
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  ctx.fillStyle = est.color;
  ctx.font = '600 12px "Segoe UI", sans-serif';
  ctx.fillText(est.icono + '  ' + etiqueta, margen.izquierda, 2);
  ctx.font = '11px "Segoe UI", sans-serif';
  const segs = [];
  let ac = [];
  puntos.forEach(p => {
    if (p[serie] === null || p[serie] === undefined) {
      if (ac.length > 1) segs.push(ac);
      ac = [];
    } else { ac.push(p); }
  });
  if (ac.length > 1) segs.push(ac);
  lienzo._segs = segs;
  lienzo._X = X;
  lienzo._Y = Y;
  lienzo._margen = margen;
  lienzo._w = w;
  lienzo._h = h;
  lienzo._estilo = est;
  lienzo._serie = serie;
  lienzo._vminG = vmin;
  dibujarCuerpo(lienzo, puntos, serie);
  return dibujarDetalles(lienzo, puntos, serie);
}
function dibujarCuerpo(lienzo, puntos, serie) {
  const ctx = lienzo.getContext('2d');
  const est = lienzo._estilo;
  const X = lienzo._X;
  const Y = lienzo._Y;
  const margen = lienzo._margen;
  const w = lienzo._w;
  const h = lienzo._h;
  const segs = lienzo._segs;
  if (est.tipo === 'barras') {
    const base = Y(lienzo._vminG);
    const paso = w / Math.max(1, puntos.length);
    const ab = Math.min(14, Math.max(2, paso * 0.62));
    puntos.forEach(p => {
      if (p[serie] === null || p[serie] === undefined || p[serie] <= 0) return;
      const px = X(new Date(p.t).getTime());
      const py = Y(p[serie]);
      const g = ctx.createLinearGradient(0, py, 0, base);
      g.addColorStop(0, est.color);
      g.addColorStop(1, est.colorSuave);
      ctx.fillStyle = g;
      const bx = Math.min(Math.max(px - ab / 2, margen.izquierda), margen.izquierda + w - ab);
      const bh = Math.max(1, base - py);
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(bx, py, ab, bh, [3, 3, 0, 0]);
      else ctx.rect(bx, py, ab, bh);
      ctx.fill();
    });
    return;
  }
  const baseY = est.tipo === 'picos' ? Y(0) : Y(lienzo._vminG);
  segs.forEach(sg => {
    if (est.tipo === 'linea') trazarRecto2(ctx, X, Y, sg, serie);
    else trazarSuave2(ctx, X, Y, sg, serie);
    const g = ctx.createLinearGradient(0, margen.arriba, 0, margen.arriba + h);
    g.addColorStop(0, est.colorSuave);
    g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.save();
    ctx.lineTo(X(new Date(sg[sg.length - 1].t).getTime()), baseY);
    ctx.lineTo(X(new Date(sg[0].t).getTime()), baseY);
    ctx.closePath();
    ctx.fillStyle = g;
    ctx.fill();
    ctx.restore();
  });
  ctx.strokeStyle = est.color;
  ctx.lineWidth = serie === 'presion_barometrica' ? 1.6 : 2.4;
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  ctx.shadowColor = est.color;
  ctx.shadowBlur = 8;
  segs.forEach(sg => {
    if (est.tipo === 'linea') trazarRecto2(ctx, X, Y, sg, serie);
    else trazarSuave2(ctx, X, Y, sg, serie);
    ctx.stroke();
  });
  ctx.shadowBlur = 0;
}

function dibujarDetalles(lienzo, puntos, serie) {
  const ctx = lienzo.getContext('2d');
  const est = lienzo._estilo;
  const X = lienzo._X;
  const Y = lienzo._Y;
  const margen = lienzo._margen;
  const w = lienzo._w;
  const h = lienzo._h;
  const vals = puntos.map(p => p[serie]).filter(v => v !== null && v !== undefined);
  if (!vals.length) return null;
  const suma = vals.reduce((a, b) => a + b, 0);
  const stats = {
    min: Math.min.apply(null, vals),
    max: Math.max.apply(null, vals),
    avg: suma / vals.length,
    total: suma
  };
  lienzo._stats = stats;
  const esBarras = est.tipo === 'barras';
  const marcar = (b, r, rel) => {
    const p = puntos.find(q => q[serie] === b);
    if (!p) return;
    const px = X(new Date(p.t).getTime());
    const py = Y(b);
    ctx.beginPath(); ctx.arc(px, py, r + 3, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(255,255,255,0.25)'; ctx.fill();
    ctx.beginPath(); ctx.arc(px, py, r, 0, Math.PI * 2);
    ctx.fillStyle = rel; ctx.fill();
    ctx.lineWidth = 2; ctx.strokeStyle = '#0b0a1f'; ctx.stroke();
  };
  if (!esBarras && serie === 'presion_barometrica') {
    ctx.save();
    ctx.setLineDash([6, 5]);
    ctx.strokeStyle = est.color;
    ctx.globalAlpha = 0.7;
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(margen.izquierda, Y(stats.avg));
    ctx.lineTo(margen.izquierda + w, Y(stats.avg));
    ctx.stroke();
    ctx.restore();
    ctx.fillStyle = est.color;
    ctx.textAlign = 'right';
    ctx.textBaseline = 'bottom';
    ctx.fillText('prom ' + formatear(stats.avg, 1), margen.izquierda + w - 2, Y(stats.avg) - 6);
  }
  if (!esBarras && serie === 'temperatura') {
    marcar(stats.max, 4, '#ef4444');
    marcar(stats.min, 4, est.color);
  } else if (!esBarras && serie === 'radiacion_solar') {
    marcar(stats.max, 5, '#fde047');
  } else if (!esBarras) {
    for (let i = puntos.length - 1; i >= 0; i--) {
      if (puntos[i][serie] !== null && puntos[i][serie] !== undefined) {
        const px = X(new Date(puntos[i].t).getTime());
        const py = Y(puntos[i][serie]);
        ctx.beginPath(); ctx.arc(px, py, 4, 0, Math.PI * 2);
        ctx.fillStyle = est.color; ctx.fill();
        ctx.lineWidth = 2; ctx.strokeStyle = '#fff'; ctx.stroke();
        break;
      }
    }
  }
  ctx.fillStyle = '#94a3b8';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  const tiempos = puntos.map(p => new Date(p.t).getTime());
  const tmin = Math.min.apply(null, tiempos);
  const tmax = Math.max.apply(null, tiempos);
  const rangoT = (tmax - tmin) || 1;
  for (let i = 0; i < 6; i++) {
    const t = tmin + (rangoT * i) / 5;
    const px = X(t);
    const f = new Date(t);
    const hh = f.getHours();
    const ap = hh >= 12 ? 'p. m.' : 'a. m.';
    const h12 = hh % 12 === 0 ? 12 : hh % 12;
    const mm = String(f.getMinutes()).padStart(2, '0');
    ctx.fillText(h12 + ':' + mm + ' ' + ap, px, margen.arriba + h + 8);
  }
  return stats;
}


/* OVERRIDE 2: pie con min/max/prom + color del boton activo. */
(function () {
  const _orig = dibujarGrafica;
  window.dibujarGrafica = function (lienzo, puntos, serie, etiqueta) {
    const r = _orig(lienzo, puntos, serie, etiqueta);
    try {
      const tarjeta = lienzo.closest('.grafica-tarjeta');
      const est = typeof estiloDe === 'function' ? estiloDe(serie) : null;
      if (tarjeta && est) tarjeta.style.setProperty('--acento-serie', est.color);
      if (tarjeta) {
        tarjeta.querySelectorAll('.js-selector button').forEach(b => {
          const on = b.dataset.serie === serie;
          b.classList.toggle('activo', on);
        });
        const statsEl = tarjeta.querySelector('.js-stats');
        const st = lienzo._stats || r;
        if (statsEl && st) {
          if (serie === 'precipitacion') {
            statsEl.textContent = 'Total: ' + formatear(st.total, 1) + ' mm  |  Max: ' + formatear(st.max, 1) + ' mm';
          } else {
            statsEl.textContent = 'Min: ' + formatear(st.min, est.dec) + ' ' + est.unidad +
              '  |  Max: ' + formatear(st.max, est.dec) + ' ' + est.unidad +
              '  |  Prom: ' + formatear(st.avg, est.dec) + ' ' + est.unidad;
          }
          statsEl.title = est.detalle || '';
        }
      }
    } catch (e) { /* no rompe la grafica */ }
    return r;
  };
})();
