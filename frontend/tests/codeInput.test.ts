import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
    CODE_ALPHABET,
    CODE_LENGTH,
    EMPTY_BOXES,
    applyInput,
    backspace,
    cleanChars,
    isComplete,
    retryAfterSeconds,
} from '../src/codeInput.ts';

const boxes = (text: string) => Array.from({ length: CODE_LENGTH }, (_, i) => text[i] ?? '');

test('the alphabet is the server one, without look-alikes', () => {
    assert.equal(CODE_ALPHABET, '23456789ABCDEFGHJKMNPQRSTUVWXYZ');
    assert.equal(CODE_LENGTH, 6);
});

test('cleanChars uppercases and drops anything outside the alphabet', () => {
    assert.equal(cleanChars('k7m 2x9'), 'K7M2X9');
    assert.equal(cleanChars('K7M-2X9'), 'K7M2X9');
    assert.equal(cleanChars('0O1IL!'), '');
});

test('typing a valid character fills the box and moves on', () => {
    const r = applyInput(EMPTY_BOXES, 0, 'k');
    assert.deepEqual(r.boxes, boxes('K'));
    assert.equal(r.focus, 1);
});

test('typing in the last box stays on the last box', () => {
    const r = applyInput(boxes('K7M2X'), 5, '9');
    assert.deepEqual(r.boxes, boxes('K7M2X9'));
    assert.equal(r.focus, 5);
});

test('characters outside the alphabet are ignored', () => {
    const r = applyInput(boxes('K'), 1, 'o');
    assert.deepEqual(r.boxes, boxes('K'));
    assert.equal(r.focus, 1);
});

test('typing next to the character already in a box replaces it', () => {
    assert.deepEqual(applyInput(boxes('K7'), 1, '7M').boxes, boxes('KM'));
    assert.deepEqual(applyInput(boxes('K7'), 1, 'M7').boxes, boxes('KM'));
    assert.deepEqual(applyInput(boxes('K7'), 1, '77').boxes, boxes('K7'));
});

test('an emptied box is cleared', () => {
    const r = applyInput(boxes('K7'), 1, '');
    assert.deepEqual(r.boxes, boxes('K'));
    assert.equal(r.focus, 1);
});

test('pasting fills all six, ignoring spaces, dashes and case', () => {
    const r = applyInput(EMPTY_BOXES, 3, 'k7m-2x9 ');
    assert.deepEqual(r.boxes, boxes('K7M2X9'));
    assert.equal(r.focus, 5);
});

test('pasting extra characters keeps the first six', () => {
    assert.deepEqual(applyInput(EMPTY_BOXES, 0, 'K7M2X9ABC').boxes, boxes('K7M2X9'));
});

test('pasting a short text fills from the start and focuses the next box', () => {
    const r = applyInput(boxes('ZZZ'), 2, 'K7M');
    assert.deepEqual(r.boxes, boxes('K7M'));
    assert.equal(r.focus, 3);
});

test('backspace clears a filled box and stays there', () => {
    const r = backspace(boxes('K7M'), 2);
    assert.deepEqual(r.boxes, boxes('K7'));
    assert.equal(r.focus, 2);
});

test('backspace in an empty box clears the previous box and moves back', () => {
    const r = backspace(boxes('K7M'), 3);
    assert.deepEqual(r.boxes, boxes('K7'));
    assert.equal(r.focus, 2);
});

test('backspace in the first empty box does nothing', () => {
    const r = backspace(EMPTY_BOXES, 0);
    assert.deepEqual(r.boxes, EMPTY_BOXES);
    assert.equal(r.focus, 0);
});

test('isComplete needs all six boxes', () => {
    assert.equal(isComplete(boxes('K7M2X')), false);
    assert.equal(isComplete(boxes('K7M2X9')), true);
});

test('retryAfterSeconds reads the header and never returns less than one', () => {
    assert.equal(retryAfterSeconds('30'), 30);
    assert.equal(retryAfterSeconds('0'), 1);
    assert.equal(retryAfterSeconds(null), 10);
    assert.equal(retryAfterSeconds('soon'), 10);
});
