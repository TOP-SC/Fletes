/**
 * TOP · Menú calculadora portfolio
 * ─────────────────────────────────────────────────────────────────
 * Instalación en el Google Sheet «Seguimiento de Automatizaciones»:
 *   1. Extensiones → Apps Script
 *   2. Pegar este archivo (borrar Code.gs vacío si hace falta)
 *   3. Editar CALC_URL abajo con la URL donde hospedás CALCULADORA_PORTFOLIO_TOP.html
 *      (SharePoint, GitHub Pages, servidor interno, etc.)
 *   4. Guardar → Ejecutar una vez «onOpen» o recargar el sheet
 *
 * El menú abre la calculadora con el ID del libro y la pestaña activa (gid),
 * para que sincronice automáticamente esa hoja.
 */

/** Cambiar por la URL pública del HTML (obligatorio para el menú del sheet). */
var CALC_URL = 'https://TU-SERVIDOR/docs/CALCULADORA_PORTFOLIO_TOP.html';

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('TOP · Calculadora')
    .addItem('Abrir portfolio (sincronizado)', 'abrirCalculadoraPortfolio')
    .addItem('Abrir portfolio — pestaña Listado', 'abrirCalculadoraListado')
    .addSeparator()
    .addItem('Copiar enlace de sync', 'copiarEnlaceSync')
    .addToUi();
}

/**
 * GID fijo de la pestaña Listado / Automatizaciones si siempre es la misma.
 * Si no, se usa la pestaña activa.
 */
var GID_LISTADO = '1156348848';

function urlCalculadora_(gid) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var id = ss.getId();
  var base = CALC_URL;
  if (base.indexOf('TU-SERVIDOR') >= 0) {
    SpreadsheetApp.getUi().alert(
      'Configurá CALC_URL en Apps Script con la URL donde está CALCULADORA_PORTFOLIO_TOP.html'
    );
    return null;
  }
  var sep = base.indexOf('?') >= 0 ? '&' : '?';
  return base + sep + 'id=' + id + '&gid=' + gid + '&auto=1';
}

function abrirCalculadoraPortfolio() {
  var sheet = SpreadsheetApp.getActiveSheet();
  var url = urlCalculadora_(sheet.getSheetId());
  if (!url) return;
  abrirUrl_(url);
}

function abrirCalculadoraListado() {
  var url = urlCalculadora_(GID_LISTADO);
  if (!url) return;
  abrirUrl_(url);
}

function copiarEnlaceSync() {
  var sheet = SpreadsheetApp.getActiveSheet();
  var url = urlCalculadora_(sheet.getSheetId());
  if (!url) return;
  var html = HtmlService.createHtmlOutput(
    '<p style="font-family:sans-serif">Enlace (copiá manualmente):</p>' +
    '<textarea style="width:100%;height:80px" onclick="this.select()">' + url + '</textarea>'
  ).setWidth(420).setHeight(140);
  SpreadsheetApp.getUi().showModalDialog(html, 'Enlace calculadora portfolio');
}

function abrirUrl_(url) {
  var safe = url.replace(/"/g, '&quot;');
  var html = HtmlService.createHtmlOutput(
    '<script>window.open("' + safe + '","_blank");google.script.host.close();<\/script>'
  ).setWidth(80).setHeight(40);
  SpreadsheetApp.getUi().showModalDialog(html, 'Abriendo calculadora…');
}

/**
 * Opcional: al editar celdas de horas, podés registrar en log (no empuja al navegador).
 * La calculadora HTML ya hace polling cada 1 min si está abierta.
 */
function onEdit(e) {
  if (!e || !e.range) return;
  var col = e.range.getColumn();
  var header = e.range.getSheet().getRange(1, col).getValue();
  var h = String(header).toLowerCase();
  if (h.indexOf('horas invertidas') >= 0 || h.indexOf('reduccion') >= 0) {
    // Reservado: futuro webhook o sidebar embebido
  }
}
