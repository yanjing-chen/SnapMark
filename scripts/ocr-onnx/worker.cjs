"use strict";
/* GitHub-hosted dependency proof for SnapMark's future standalone ONNX OCR.
   This is NOT yet wired into SnapMark's image recognition path. */
const fs = require('fs');
const ort = require('onnxruntime-node');
const ocr = require('esearch-ocr');
const canvas = require('canvas');
if (process.argv.includes('--self-test')) {
  if (typeof ort.InferenceSession?.create !== 'function' ||
      typeof ocr.init !== 'function' ||
      typeof canvas.createCanvas !== 'function') {
    process.exitCode = 1;
    process.stderr.write('Missing OCR runtime exports\n');
  } else {
    process.stdout.write('SNAPMARK_ONNX_COMPONENTS=PASS\n');
  }
} else {
  process.stderr.write('ONNX OCR inference will be enabled after model integration tests.\n');
  process.exitCode = 2;
}
