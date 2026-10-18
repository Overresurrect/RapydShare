// The logic of the six code boxes, kept apart from React so it can be tested.

export const CODE_ALPHABET = '23456789ABCDEFGHJKMNPQRSTUVWXYZ';
export const CODE_LENGTH = 6;
export const EMPTY_BOXES: string[] = Array.from({ length: CODE_LENGTH }, () => '');

const DEFAULT_WAIT = 10;

export interface BoxUpdate {
    boxes: string[];
    focus: number;
}

/** text as uppercase code characters, with everything else dropped. */
export function cleanChars(text: string): string {
    return Array.from(text.toUpperCase()).filter(c => CODE_ALPHABET.includes(c)).join('');
}

export function isComplete(boxes: string[]): boolean {
    return boxes.every(c => c !== '');
}

/** What a box's new value means: one typed character, or a whole code pasted or autofilled. */
export function applyInput(boxes: string[], index: number, value: string): BoxUpdate {
    if (value === '') return { boxes: boxes.map((c, i) => (i === index ? '' : c)), focus: index };

    let chars = cleanChars(value);
    const previous = boxes[index];
    // The caret sat after the old character, so the new one is whichever differs
    if (previous && chars.length === 2) chars = chars[0] === previous ? chars[1] : chars[0];
    if (chars.length === 0) return { boxes, focus: index };

    if (chars.length === 1) {
        return {
            boxes: boxes.map((c, i) => (i === index ? chars : c)),
            focus: Math.min(index + 1, CODE_LENGTH - 1),
        };
    }

    const filled = chars.slice(0, CODE_LENGTH);
    return {
        boxes: EMPTY_BOXES.map((_, i) => filled[i] ?? ''),
        focus: Math.min(filled.length, CODE_LENGTH - 1),
    };
}

export function backspace(boxes: string[], index: number): BoxUpdate {
    if (boxes[index] !== '') return { boxes: boxes.map((c, i) => (i === index ? '' : c)), focus: index };
    if (index === 0) return { boxes, focus: 0 };
    return { boxes: boxes.map((c, i) => (i === index - 1 ? '' : c)), focus: index - 1 };
}

/** The wait in seconds from a Retry-After header. */
export function retryAfterSeconds(header: string | null): number {
    const seconds = Number.parseInt(header ?? '', 10);
    return Number.isNaN(seconds) ? DEFAULT_WAIT : Math.max(seconds, 1);
}
