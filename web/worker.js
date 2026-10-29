// Version pinned to the official Pyodide release. The CSV never leaves this worker.
const RUNTIME_URL = 'https://cdn.jsdelivr.net/pyodide/v314.0.7/full/';
const SOURCES = ['__init__.py', 'questions.py', 'qti_builder.py', 'canvas_qti12.py', 'template.py', 'browser_bridge.py'];

async function initialize() {
  const { loadPyodide } = await import(`${RUNTIME_URL}pyodide.mjs`);
  const runtime = await loadPyodide({ indexURL: RUNTIME_URL });
  runtime.FS.mkdirTree('/app/qti_converter');
  runtime.FS.mkdirTree('/work');
  await Promise.all(SOURCES.map(async (name) => {
    const response = await fetch(new URL(`./python/qti_converter/${name}`, import.meta.url));
    if (!response.ok) throw new Error('No se pudo cargar el conversor. Recarga la página.');
    runtime.FS.writeFile(`/app/qti_converter/${name}`, await response.text());
  }));
  runtime.runPython("import sys\nsys.path.insert(0, '/app')\nfrom qti_converter.browser_bridge import handle_request");
  self.postMessage({ type: 'ready' });
  return runtime;
}

let startupError;
const startup = initialize().catch((error) => {
  startupError = error;
  self.postMessage({ type: 'startup-error', error: 'No se pudo preparar el conversor. Comprueba tu conexión y vuelve a intentarlo.' });
});

self.onmessage = async ({ data }) => {
  const { id, action, buffer, filename, title, format } = data;
  try {
    const runtime = await startup;
    if (startupError || !runtime) throw startupError || new Error('Conversor no disponible.');
    if (action === 'analyze') runtime.FS.writeFile('/work/input.csv', new Uint8Array(buffer));
    runtime.globals.set('request_json', JSON.stringify({ action, filename, title, format, input_path: '/work/input.csv', destination: '/work/export' }));
    const result = JSON.parse(runtime.runPython('handle_request(request_json)'));
    if (action === 'generate') {
      const bytes = runtime.FS.readFile(result.path);
      self.postMessage({ id, result, buffer: bytes.buffer }, [bytes.buffer]);
      // A completed download does not need to remain in the worker filesystem.
      runtime.runPython("import shutil\nshutil.rmtree('/work/export', ignore_errors=True)");
    } else {
      self.postMessage({ id, result });
    }
  } catch (error) {
    const details = String(error?.message || error);
    const match = details.match(/(?:ValidationError|ValueError): ([\s\S]*?)\s*$/);
    self.postMessage({ id, error: match ? match[1] : 'No se pudo completar la conversión. Revisa el archivo o vuelve a intentarlo.' });
  } finally {
    // Only request metadata is placed in Python globals; user text is never code.
  }
};
