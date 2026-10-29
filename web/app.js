const $ = (id) => document.getElementById(id);
const types = { mc: 'Opción única', ma: 'Selección múltiple', tf: 'Verdadero / falso', short: 'Respuesta corta', blank: 'Espacio en blanco', essay: 'Ensayo' };
let worker;
let ready = false;
let busy = false;
let analysis = null;
let selectedFile = null;
let revision = 0;
let sequence = 0;
let downloadURL;
const pending = new Map();

function updateButton() {
  $('generate').disabled = !ready || busy || !analysis || !$('exam-title').value.trim();
  $('generate').textContent = busy ? 'Procesando…' : 'Generar paquete QTI ↓';
  $('exam-title').disabled = busy;
  $('qti-format').disabled = busy;
  $('csv-file').disabled = busy;
  $('remove-file').disabled = busy;
}

function clearResult() {
  $('result').hidden = true;
  if (downloadURL) URL.revokeObjectURL(downloadURL);
  downloadURL = null;
}

function showError(message = '') {
  $('error').textContent = message;
  $('error').hidden = !message;
}

function request(action, payload = {}, transfer = []) {
  const id = ++sequence;
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      pending.delete(id);
      reject(new Error('La operación está tardando demasiado. Vuelve a cargar la página e inténtalo otra vez.'));
    }, 180000);
    pending.set(id, { resolve, reject, timeout });
    worker.postMessage({ id, action, ...payload }, transfer);
  });
}

function startWorker() {
  worker?.terminate();
  for (const entry of pending.values()) {
    clearTimeout(entry.timeout);
    entry.reject(new Error('El conversor se ha reiniciado. Selecciona de nuevo tu archivo.'));
  }
  pending.clear();
  ready = false;
  $('runtime').className = 'runtime';
  $('runtime-text').textContent = 'Preparando el conversor. La primera carga puede tardar unos segundos…';
  $('retry').hidden = true;
  updateButton();
  worker = new Worker(new URL('./worker.js', import.meta.url), { type: 'module' });
  const timer = setTimeout(() => startupFailed(), 120000);
  function startupFailed() {
    clearTimeout(timer);
    ready = false;
    $('runtime').className = 'runtime failed';
    $('runtime-text').textContent = 'No se pudo cargar el conversor. Comprueba tu conexión y reintenta.';
    $('retry').hidden = false;
    updateButton();
  }
  worker.onmessage = ({ data }) => {
    if (data.type === 'ready') {
      clearTimeout(timer);
      ready = true;
      $('runtime').className = 'runtime ready';
      $('runtime-text').textContent = 'Conversor listo · procesamiento local en tu navegador';
      updateButton();
    } else if (data.type === 'startup-error') {
      startupFailed();
      for (const entry of pending.values()) {
        clearTimeout(entry.timeout);
        entry.reject(new Error(data.error));
      }
      pending.clear();
    } else if (pending.has(data.id)) {
      const entry = pending.get(data.id);
      clearTimeout(entry.timeout);
      pending.delete(data.id);
      data.error ? entry.reject(new Error(data.error)) : entry.resolve(data);
    }
  };
  worker.onerror = () => startupFailed();
}

function renderAnalysis(result) {
  $('preview').hidden = false;
  $('preview-subtitle').textContent = `${result.count} ${result.count === 1 ? 'pregunta validada' : 'preguntas validadas'} antes de exportar.`;
  $('total-points').textContent = `${result.points.toLocaleString('es')} puntos`;
  $('file-details').textContent = `${result.count} preguntas · ${(selectedFile.size / 1024).toLocaleString('es', { maximumFractionDigits: 1 })} KB`;
  $('type-summary').replaceChildren(...Object.entries(result.types).map(([tipo, count]) => {
    const tag = document.createElement('span');
    tag.textContent = `${count} · ${types[tipo]}`;
    return tag;
  }));
  $('question-list').replaceChildren(...result.questions.map((q, index) => {
    const row = document.createElement('article');
    row.className = 'question-row';
    const number = document.createElement('span');
    number.className = 'question-number';
    number.textContent = String(index + 1).padStart(2, '0');
    const content = document.createElement('div');
    content.className = 'question-content';
    const title = document.createElement('h3');
    title.textContent = q.title;
    const text = document.createElement('p');
    text.textContent = q.text.replace('{{respuesta}}', '________');
    const meta = document.createElement('span');
    meta.className = 'question-meta';
    meta.textContent = `${types[q.tipo]} · ${q.points} puntos · ${q.feedback_count} comentarios · ${q.tipo === 'essay' ? 'Revisión manual' : 'Correcta: ' + q.answers.join(' / ')}`;
    content.append(title, text, meta);
    row.append(number, content);
    return row;
  }));
  if (result.count > result.questions.length) {
    const note = document.createElement('p');
    note.className = 'preview-more';
    note.textContent = `Se muestran las primeras ${result.questions.length}; se exportarán las ${result.count} preguntas.`;
    $('question-list').append(note);
  }
}

async function selectFile(file) {
  if (!file || busy) return;
  const currentRevision = ++revision;
  analysis = null;
  selectedFile = null;
  clearResult();
  showError();
  $('preview').hidden = true;
  $('file-summary').hidden = true;
  if (!file.name.toLowerCase().endsWith('.csv')) {
    showError('Selecciona un archivo con extensión .csv.');
    updateButton();
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    showError('El archivo supera el límite de 10 MB. Divide el banco en archivos más pequeños.');
    updateButton();
    return;
  }
  selectedFile = file;
  $('file-name').textContent = file.name;
  $('file-details').textContent = 'Validando preguntas…';
  $('file-summary').hidden = false;
  busy = true;
  updateButton();
  try {
    const buffer = await file.arrayBuffer();
    const { result } = await request('analyze', { buffer, filename: file.name }, [buffer]);
    if (currentRevision !== revision) return;
    analysis = result;
    if (!$('exam-title').value.trim()) $('exam-title').value = result.suggested_title;
    renderAnalysis(result);
  } catch (error) {
    if (currentRevision !== revision) return;
    showError(error.message);
    $('file-details').textContent = 'El archivo requiere correcciones.';
  } finally {
    if (currentRevision === revision) {
      busy = false;
      updateButton();
    }
  }
}

$('csv-file').addEventListener('change', (event) => selectFile(event.target.files[0]));
$('remove-file').addEventListener('click', () => {
  ++revision;
  analysis = null;
  selectedFile = null;
  $('csv-file').value = '';
  $('file-summary').hidden = true;
  $('preview').hidden = true;
  clearResult();
  showError();
  updateButton();
});
$('exam-title').addEventListener('input', () => { clearResult(); updateButton(); });
$('qti-format').addEventListener('change', () => {
  clearResult();
  $('format-help').textContent = $('qti-format').value === '1.2'
    ? 'Perfil con tipos y feedback explícitos para importar en Canvas.'
    : 'Canvas puede omitir feedback QTI 2.1. Comprueba los comentarios después de importar.';
});
$('retry').addEventListener('click', () => {
  const previous = selectedFile;
  analysis = null;
  busy = false;
  startWorker();
  if (previous) selectFile(previous);
});
for (const type of ['dragenter', 'dragover']) $('dropzone').addEventListener(type, (event) => {
  event.preventDefault();
  if (!busy) $('dropzone').classList.add('dragging');
});
for (const type of ['dragleave', 'drop']) $('dropzone').addEventListener(type, (event) => {
  event.preventDefault();
  $('dropzone').classList.remove('dragging');
});
$('dropzone').addEventListener('drop', (event) => selectFile(event.dataTransfer.files[0]));
window.addEventListener('dragover', (event) => event.preventDefault());
window.addEventListener('drop', (event) => event.preventDefault());
$('generate').addEventListener('click', async () => {
  if (!analysis || busy || !ready || !$('exam-title').value.trim()) return;
  busy = true;
  clearResult();
  showError();
  updateButton();
  try {
    const { result, buffer } = await request('generate', { title: $('exam-title').value.trim(), format: $('qti-format').value });
    downloadURL = URL.createObjectURL(new Blob([buffer], { type: 'application/zip' }));
    $('download').href = downloadURL;
    $('download').download = result.filename;
    $('result-description').textContent = `${result.count} preguntas · ${result.filename}${result.warnings.length ? '\n' + result.warnings.join('\n') : ''}`;
    $('result').hidden = false;
    $('download').focus();
  } catch (error) {
    showError(error.message);
  } finally {
    busy = false;
    updateButton();
  }
});
startWorker();
