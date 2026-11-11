import { test } from 'node:test';
import assert from 'node:assert/strict';
import { kindOf, presentKinds, filterItems, keepFilter, nextSort, parseSort, sortLabel, arrange, shortDate } from '../src/arrange.ts';
import type { Section, Sort } from '../src/arrange.ts';
import type { FileItem } from '../src/types.ts';

function item(name: string, opts: Partial<FileItem> = {}): FileItem {
    return { name, path: name, is_dir: false, size: 0, mtime: 0, mime: null, type: 'file', ...opts };
}

// --- File kinds ---

test('the mime type the server sends decides the kind', () => {
    assert.equal(kindOf(item('a.jpg', { mime: 'image/jpeg', type: 'image' })), 'photo');
    assert.equal(kindOf(item('a.mp4', { mime: 'video/mp4', type: 'video' })), 'video');
    assert.equal(kindOf(item('a.mp3', { mime: 'audio/mpeg' })), 'audio');
    assert.equal(kindOf(item('a.pdf', { mime: 'application/pdf' })), 'document');
    assert.equal(kindOf(item('a.py', { mime: 'text/x-python' })), 'document');
    assert.equal(kindOf(item('a.zip', { mime: 'application/zip' })), 'archive');
});

test('the extension decides when the server has no mime type', () => {
    assert.equal(kindOf(item('IMG_0451.heic')), 'photo');
    assert.equal(kindOf(item('CLIP.MOV')), 'video');
    assert.equal(kindOf(item('memo.m4a')), 'audio');
    assert.equal(kindOf(item('Resume.docx')), 'document');
    assert.equal(kindOf(item('backup.7z')), 'archive');
});

test('a folder is a folder whatever its name', () => {
    assert.equal(kindOf(item('holiday.zip', { is_dir: true, type: 'folder' })), 'folder');
});

test('anything unrecognised is Other', () => {
    assert.equal(kindOf(item('setup.exe', { mime: 'application/x-msdownload' })), 'other');
    assert.equal(kindOf(item('README')), 'other');
    assert.equal(kindOf(item('blob.bin', { mime: 'application/octet-stream' })), 'other');
});

// --- Chips ---

test('only the kinds in the folder get a chip, in a fixed order, with counts', () => {
    const items = [
        item('b.zip'),
        item('a.jpg', { mime: 'image/jpeg', type: 'image' }),
        item('Trip', { is_dir: true, type: 'folder' }),
        item('c.png', { mime: 'image/png', type: 'image' }),
    ];
    assert.deepEqual(
        presentKinds(items).map(k => [k.kind, k.count]),
        [['folder', 1], ['photo', 2], ['archive', 1]],
    );
});

test('search and the type chip narrow the list together', () => {
    const items = [
        item('beach.jpg', { mime: 'image/jpeg', type: 'image' }),
        item('Beach.mp4', { mime: 'video/mp4', type: 'video' }),
        item('city.jpg', { mime: 'image/jpeg', type: 'image' }),
    ];
    const names = (list: FileItem[]) => list.map(i => i.name);
    assert.deepEqual(names(filterItems(items, 'BEACH', 'photo')), ['beach.jpg']);
    assert.deepEqual(names(filterItems(items, 'beach', null)), ['beach.jpg', 'Beach.mp4']);
    assert.deepEqual(names(filterItems(items, '', 'photo')), ['beach.jpg', 'city.jpg']);
    assert.deepEqual(names(filterItems(items, '', null)), ['beach.jpg', 'Beach.mp4', 'city.jpg']);
});

test('refreshing a folder keeps its type filter, loading any other folder clears it', () => {
    const photosAtHome = { path: '', kind: 'photo' } as const;
    assert.deepEqual(keepFilter(photosAtHome, ''), photosAtHome);
    assert.equal(keepFilter(photosAtHome, 'Trip to Goa'), null);
    assert.equal(keepFilter(null, ''), null);
});

// --- Sort tabs ---

test('tapping a new sort tab starts from its most useful direction', () => {
    const byName = { key: 'name', dir: 'asc' } as const;
    assert.deepEqual(nextSort(byName, 'date'), { key: 'date', dir: 'desc' });
    assert.deepEqual(nextSort(byName, 'size'), { key: 'size', dir: 'desc' });
    assert.deepEqual(nextSort(byName, 'type'), { key: 'type', dir: 'desc' });
    assert.deepEqual(nextSort({ key: 'date', dir: 'asc' }, 'name'), { key: 'name', dir: 'asc' });
});

test('tapping the active sort tab again reverses it', () => {
    assert.deepEqual(nextSort({ key: 'date', dir: 'desc' }, 'date'), { key: 'date', dir: 'asc' });
    assert.deepEqual(nextSort({ key: 'name', dir: 'asc' }, 'name'), { key: 'name', dir: 'desc' });
    assert.deepEqual(nextSort({ key: 'type', dir: 'asc' }, 'type'), { key: 'type', dir: 'desc' });
});

test('a remembered sort is read back, and anything unreadable falls back to name A–Z', () => {
    assert.deepEqual(parseSort('size', 'asc'), { key: 'size', dir: 'asc' });
    assert.deepEqual(parseSort(null, null), { key: 'name', dir: 'asc' });
    assert.deepEqual(parseSort('colour', 'desc'), { key: 'name', dir: 'asc' });
    assert.deepEqual(parseSort('date', 'sideways'), { key: 'date', dir: 'desc' });
});

test('the status line names the direction in words that match the sort', () => {
    assert.equal(sortLabel({ key: 'name', dir: 'desc' }), 'Name, Z–A');
    assert.equal(sortLabel({ key: 'date', dir: 'asc' }), 'Date, oldest first');
    assert.equal(sortLabel({ key: 'size', dir: 'desc' }), 'Size, largest first');
    // Type sections are newest first inside, like sorting by date
    assert.equal(sortLabel({ key: 'type', dir: 'desc' }), 'Type, newest first');
});

// --- Sorting and sections ---

// Wednesday 11 November 2026, 3 pm local time
const NOW = new Date(2026, 10, 11, 15, 0);
const at = (month: number, day: number, hour = 12, year = 2026) => new Date(year, month, day, hour).getTime() / 1000;
const MB = 1024 * 1024;

const FOLDER = (name: string, mtime: number, size: number) =>
    item(name, { is_dir: true, type: 'folder', mtime, size });
const PHOTO = (name: string, mtime: number, size: number) =>
    item(name, { mime: 'image/jpeg', type: 'image', mtime, size });
const VIDEO = (name: string, mtime: number, size: number) =>
    item(name, { mime: 'video/mp4', type: 'video', mtime, size });

const FOLDER_ITEMS = [
    // Directory sizes from the server mean nothing, so these must not decide any order
    FOLDER('Trip to Goa', at(9, 22), 4096),
    FOLDER('Screenshots', at(10, 8), 96),
    PHOTO('IMG_10.jpg', at(10, 11, 9), 2.8 * MB),
    PHOTO('IMG_2.jpg', at(10, 11, 10), 3.1 * MB),
    PHOTO('IMG_0451.heic', at(10, 10, 8), 2.4 * MB),
    PHOTO('beach.jpg', at(10, 6), 4.2 * MB),
    VIDEO('VID_0012.mp4', at(10, 10, 18), 184 * MB),
    VIDEO('birthday.mov', at(9, 2), 640 * MB),
    item('Invoice.pdf', { mime: 'application/pdf', mtime: at(9, 30), size: 220 * 1024 }),
    item('Resume.docx', { mtime: at(8, 2), size: 48 * 1024 }),
    item('backup.zip', { mime: 'application/zip', mtime: at(7, 13), size: 1.2 * 1024 * MB }),
];

function shape(sections: Section[]) {
    return sections.map(s => [s.label, s.items.map(i => i.name)]);
}
function sorted(sort: Sort, items = FOLDER_ITEMS) {
    return shape(arrange(items, sort, NOW, 'en-US'));
}

test('by name: folders first, numbers in names in counting order, no headings', () => {
    assert.deepEqual(sorted({ key: 'name', dir: 'asc' }), [
        [null, ['Screenshots', 'Trip to Goa',
            'backup.zip', 'beach.jpg', 'birthday.mov', 'IMG_2.jpg', 'IMG_10.jpg', 'IMG_0451.heic',
            'Invoice.pdf', 'Resume.docx', 'VID_0012.mp4']],
    ]);
});

test('by name Z–A: folders still on top, both lists reversed', () => {
    assert.deepEqual(sorted({ key: 'name', dir: 'desc' }), [
        [null, ['Trip to Goa', 'Screenshots',
            'VID_0012.mp4', 'Resume.docx', 'Invoice.pdf',
            'IMG_0451.heic', 'IMG_10.jpg', 'IMG_2.jpg', 'birthday.mov', 'beach.jpg', 'backup.zip']],
    ]);
});

test('by date, newest first: folders, then recent days, then one section per month', () => {
    assert.deepEqual(sorted({ key: 'date', dir: 'desc' }), [
        ['Folders', ['Screenshots', 'Trip to Goa']],
        ['Today', ['IMG_2.jpg', 'IMG_10.jpg']],
        ['Yesterday', ['VID_0012.mp4', 'IMG_0451.heic']],
        ['Last 7 days', ['beach.jpg']],
        ['Last 30 days', ['Invoice.pdf']],
        ['October 2026', ['birthday.mov']],
        ['September 2026', ['Resume.docx']],
        ['August 2026', ['backup.zip']],
    ]);
});

test('by date, oldest first: the sections come in reverse, folders stay on top', () => {
    assert.deepEqual(sorted({ key: 'date', dir: 'asc' }), [
        ['Folders', ['Trip to Goa', 'Screenshots']],
        ['August 2026', ['backup.zip']],
        ['September 2026', ['Resume.docx']],
        ['October 2026', ['birthday.mov']],
        ['Last 30 days', ['Invoice.pdf']],
        ['Last 7 days', ['beach.jpg']],
        ['Yesterday', ['IMG_0451.heic', 'VID_0012.mp4']],
        ['Today', ['IMG_10.jpg', 'IMG_2.jpg']],
    ]);
});

test('date sections follow calendar days, not 24-hour periods', () => {
    const items = [
        PHOTO('just after midnight.jpg', at(10, 11, 0.5), 1),
        PHOTO('late yesterday.jpg', at(10, 10, 23), 1),
        PHOTO('start of 7 days.jpg', at(10, 5, 1), 1),
        PHOTO('just before 7 days.jpg', at(10, 4, 23), 1),
        PHOTO('clock ahead.jpg', at(10, 12, 9), 1),
    ];
    assert.deepEqual(sorted({ key: 'date', dir: 'desc' }, items), [
        ['Today', ['clock ahead.jpg', 'just after midnight.jpg']],
        ['Yesterday', ['late yesterday.jpg']],
        ['Last 7 days', ['start of 7 days.jpg']],
        ['Last 30 days', ['just before 7 days.jpg']],
    ]);
});

test('by size, largest first: folders by name, then files in size bands', () => {
    assert.deepEqual(sorted({ key: 'size', dir: 'desc' }), [
        ['Folders', ['Screenshots', 'Trip to Goa']],
        ['Over 1 GB', ['backup.zip']],
        ['100 MB – 1 GB', ['birthday.mov', 'VID_0012.mp4']],
        ['1 MB – 100 MB', ['beach.jpg', 'IMG_2.jpg', 'IMG_10.jpg', 'IMG_0451.heic']],
        ['Under 1 MB', ['Invoice.pdf', 'Resume.docx']],
    ]);
});

test('by size, smallest first: the bands come in reverse', () => {
    assert.deepEqual(sorted({ key: 'size', dir: 'asc' }).map(s => s[0]),
        ['Folders', 'Under 1 MB', '1 MB – 100 MB', '100 MB – 1 GB', 'Over 1 GB']);
});

test('by type: sections in a fixed order, newest first inside each', () => {
    assert.deepEqual(sorted({ key: 'type', dir: 'desc' }), [
        ['Folders', ['Screenshots', 'Trip to Goa']],
        ['Photos', ['IMG_2.jpg', 'IMG_10.jpg', 'IMG_0451.heic', 'beach.jpg']],
        ['Videos', ['VID_0012.mp4', 'birthday.mov']],
        ['Documents', ['Invoice.pdf', 'Resume.docx']],
        ['Archives', ['backup.zip']],
    ]);
});

test('by type reversed: same section order, oldest first inside each', () => {
    assert.deepEqual(sorted({ key: 'type', dir: 'asc' }), [
        ['Folders', ['Trip to Goa', 'Screenshots']],
        ['Photos', ['beach.jpg', 'IMG_0451.heic', 'IMG_10.jpg', 'IMG_2.jpg']],
        ['Videos', ['birthday.mov', 'VID_0012.mp4']],
        ['Documents', ['Resume.docx', 'Invoice.pdf']],
        ['Archives', ['backup.zip']],
    ]);
});

test('an empty folder has no sections', () => {
    assert.deepEqual(sorted({ key: 'date', dir: 'desc' }, []), []);
});

// --- Dates under thumbnails ---

test('recent dates read as Today and Yesterday, older ones as a short date', () => {
    assert.equal(shortDate(at(10, 11, 9), NOW, 'en-US'), 'Today');
    assert.equal(shortDate(at(10, 10, 23), NOW, 'en-US'), 'Yesterday');
    assert.equal(shortDate(at(10, 6), NOW, 'en-US'), 'Nov 6');
    assert.equal(shortDate(at(7, 13, 12, 2025), NOW, 'en-US'), 'Aug 13, 2025');
});
