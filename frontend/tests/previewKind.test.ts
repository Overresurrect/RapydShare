import { test } from 'node:test';
import assert from 'node:assert/strict';
import { previewKind } from '../src/previewKind.ts';

function file(name: string, mime: string | null, type: 'image' | 'video' | 'file' = 'file') {
    return { name, mime, type };
}

test('SVG goes to the sandboxed text viewer, since the server sends it as plain text', () => {
    assert.equal(previewKind(file('logo.svg', 'image/svg+xml', 'image')), 'text');
});

test('other images and videos keep their own viewers', () => {
    assert.equal(previewKind(file('photo.png', 'image/png', 'image')), 'image');
    assert.equal(previewKind(file('clip.mp4', 'video/mp4', 'video')), 'video');
});

test('PDFs and text files', () => {
    assert.equal(previewKind(file('doc.pdf', 'application/pdf')), 'pdf');
    assert.equal(previewKind(file('notes.txt', 'text/plain')), 'text');
    assert.equal(previewKind(file('script.py', null)), 'text');
});

test('anything else has no preview', () => {
    assert.equal(previewKind(file('archive.zip', 'application/zip')), 'none');
});
