'use strict';
/* SnapMark C2-022 standalone ONNX OCR worker.
 * Build dependencies on GitHub Actions, not on Code01. No model downloads or
 * PaddlePaddle installations occur in this worker.
 *
 *   node worker.cjs --self-test
 *   node worker.cjs --ocr --model-dir /path/to/model --image /path/to/pic.png
 *   node worker.cjs --smoke-test --model-dir /path/to/model
 *
 * A model directory contains det.onnx, rec.onnx and dict.txt.
 * The OCR command prints exactly one JSON object on stdout. Errors use stderr
 * and a nonzero exit code. The caller manages model installation separately.
 */
const fs = require('node:fs');
const path = require('node:path');
const ort = require('onnxruntime-node');
const ocr = require('esearch-ocr');
const { createCanvas, createImageData, loadImage } = require('canvas');

function arg(name) {
  const at = process.argv.indexOf(name);
  return at === -1 ? null : process.argv[at + 1] || null;
}
function assertFile(file, label) {
  if (!file || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    throw new Error(`${label} missing: ${file || '(not provided)'}`);
  }
}
function checkDeps() {
  if (typeof ort.InferenceSession?.create !== 'function' ||
      typeof ocr.init !== 'function' ||
      typeof ocr.setOCREnv !== 'function' ||
      typeof createCanvas !== 'function' ||
      typeof createImageData !== 'function' ||
      typeof loadImage !== 'function') {
    throw new Error('Incomplete ONNX OCR dependency exports');
  }
}
async function recognize(imagePath, modelDir) {
  checkDeps();
  assertFile(imagePath, 'Image');
  const det = path.join(modelDir, 'det.onnx');
  const rec = path.join(modelDir, 'rec.onnx');
  const dic = path.join(modelDir, 'dict.txt');
  assertFile(det, 'Detection model');
  assertFile(rec, 'Recognition model');
  assertFile(dic, 'Character dictionary');

  ocr.setOCREnv({ canvas: (w, h) => createCanvas(w, h), imageData: createImageData });
  const engine = await ocr.init({
    det: { input: det },
    rec: { input: rec, decodeDic: fs.readFileSync(dic, 'utf8') },
    ort,
  });
  const bitmap = await loadImage(imagePath);
  if (!bitmap.width || !bitmap.height || bitmap.width * bitmap.height > 25_000_000) {
    throw new Error('Invalid image dimensions or image exceeds 25 megapixels');
  }
  const canvas = createCanvas(bitmap.width, bitmap.height);
  const ctx = canvas.getContext('2d');
  ctx.drawImage(bitmap, 0, 0);
  const result = await engine.ocr(ctx.getImageData(0, 0, bitmap.width, bitmap.height));
  const raw = Array.isArray(result?.parragraphs) ? result.parragraphs :
              Array.isArray(result?.src) ? result.src : [];
  const paragraphs = raw.map(item => ({
    text: typeof item.text === 'string' ? item.text : '',
    confidence: Number.isFinite(item.mean) ? item.mean : null,
  })).filter(item => item.text.trim().length > 0);
  return { ok: true, text: paragraphs.map(p => p.text).join('\n'),
    paragraphs, engine: 'esearch-ocr', backend: 'onnxruntime-node-cpu' };
}
async function main() {
  if (process.argv.includes('--self-test')) {
    checkDeps();
    console.log('SNAPMARK_ONNX_COMPONENTS=PASS');
    return;
  }
  const modelDir = arg('--model-dir');
  if (!modelDir || !path.isAbsolute(modelDir)) {
    throw new Error('Provide an absolute --model-dir path');
  }
  if (process.argv.includes('--smoke-test')) {
    const tmp = fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'snapmark-ocr-'));
    const imagePath = path.join(tmp, 'test.png');
    try {
      const canvas = createCanvas(1100, 300);
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, 1100, 300);
      ctx.fillStyle = '#000000';
      ctx.font = 'bold 76px DejaVu Sans';
      ctx.fillText('SNAPMARK OCR 2026', 24, 120);
      ctx.font = 'bold 60px DejaVu Sans';
      ctx.fillText('HELLO 12345', 24, 240);
      fs.writeFileSync(imagePath, canvas.toBuffer('image/png'));
      const result = await recognize(imagePath, modelDir);
      if (result.text.trim().length < 4) {
        throw new Error('Real model inference returned no meaningful text');
      }
      console.log('SNAPMARK_ONNX_REAL_INFERENCE=PASS');
      console.log('RECOGNIZED_TEXT=' + JSON.stringify(result.text));
    } finally {
      fs.rmSync(tmp, { recursive: true, force: true });
    }
    return;
  }
  if (!process.argv.includes('--ocr')) {
    throw new Error('Usage: --self-test | --ocr --model-dir DIR --image FILE | --smoke-test --model-dir DIR');
  }
  const imagePath = arg('--image');
  if (!imagePath || !path.isAbsolute(imagePath)) {
    throw new Error('Provide an absolute --image path');
  }
  console.log(JSON.stringify(await recognize(imagePath, modelDir)));
}
main().catch(error => {
  process.stderr.write('SNAPMARK_ONNX_ERROR=' + (error?.stack || String(error)) + '\n');
  process.exitCode = 1;
});
