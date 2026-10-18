import { test } from 'node:test';
import assert from 'node:assert/strict';
import { uploadErrorMessage } from '../src/uploadErrors.ts';

test('known statuses get a friendly message', () => {
    assert.equal(uploadErrorMessage(413), 'File is too large');
    assert.equal(uploadErrorMessage(507), 'Not enough space on the computer');
    assert.equal(uploadErrorMessage(403), 'Uploads are turned off');
    assert.equal(uploadErrorMessage(401), 'Enter the access code again');
});

test('unknown statuses fall back to the code', () => {
    assert.equal(uploadErrorMessage(418), 'Error 418');
});
