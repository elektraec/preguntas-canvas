import { mkdir, cp } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
const output = path.join(root, 'public');
await mkdir(output, { recursive: true });
await cp(path.join(root, 'web'), output, { recursive: true });
const pythonTarget = path.join(output, 'python', 'qti_converter');
await mkdir(pythonTarget, { recursive: true });
for (const name of ['__init__.py', 'questions.py', 'qti_builder.py', 'canvas_qti12.py', 'template.py', 'browser_bridge.py']) {
  await cp(path.join(root, 'qti_converter', name), path.join(pythonTarget, name));
}
execFileSync(process.env.PYTHON || 'python', ['scripts/build_template.py', path.join(output, 'plantilla_qti.csv')], { cwd: root, stdio: 'inherit' });
console.log(`Web preparada: ${output}`);
