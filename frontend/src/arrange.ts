// Filtering, sorting and grouping the file list, kept apart from React so it can be tested.
import type { FileItem } from './types';

export type Kind = 'folder' | 'photo' | 'video' | 'audio' | 'document' | 'archive' | 'other';

// Chip order, and the order of the sections when sorting by type
export const KINDS: { kind: Kind; label: string }[] = [
    { kind: 'folder', label: 'Folders' },
    { kind: 'photo', label: 'Photos' },
    { kind: 'video', label: 'Videos' },
    { kind: 'audio', label: 'Audio' },
    { kind: 'document', label: 'Documents' },
    { kind: 'archive', label: 'Archives' },
    { kind: 'other', label: 'Other' },
];

// For files the server has no mime type for, or a vague one
const EXTENSIONS: [Kind, string[]][] = [
    ['photo', ['jpg', 'jpeg', 'png', 'gif', 'webp', 'heic', 'heif', 'avif', 'bmp', 'tif', 'tiff', 'svg', 'dng', 'raw', 'cr2', 'cr3', 'nef', 'arw']],
    ['video', ['mp4', 'mov', 'm4v', 'mkv', 'avi', 'webm', 'wmv', 'flv', '3gp', 'mpg', 'mpeg']],
    ['audio', ['mp3', 'm4a', 'aac', 'wav', 'flac', 'ogg', 'oga', 'opus', 'wma', 'aif', 'aiff', 'amr']],
    ['document', ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'odt', 'ods', 'odp', 'rtf', 'txt', 'md', 'csv',
        'pages', 'numbers', 'key', 'epub', 'json', 'xml', 'html', 'htm']],
    ['archive', ['zip', 'rar', '7z', 'tar', 'gz', 'tgz', 'bz2', 'xz', 'zst', 'dmg', 'iso']],
];

function extension(name: string): string {
    const dot = name.lastIndexOf('.');
    return dot > 0 ? name.slice(dot + 1).toLowerCase() : '';
}

export function kindOf(item: Pick<FileItem, 'name' | 'is_dir' | 'mime' | 'type'>): Kind {
    if (item.is_dir) return 'folder';
    const mime = item.mime ?? '';
    if (item.type === 'image' || mime.startsWith('image/')) return 'photo';
    if (item.type === 'video' || mime.startsWith('video/')) return 'video';
    if (mime.startsWith('audio/')) return 'audio';
    const ext = extension(item.name);
    for (const [kind, exts] of EXTENSIONS) {
        if (exts.includes(ext)) return kind;
    }
    if (mime.startsWith('text/')) return 'document';
    return 'other';
}

export function presentKinds(items: FileItem[]): { kind: Kind; label: string; count: number }[] {
    const counts = new Map<Kind, number>();
    for (const item of items) {
        const kind = kindOf(item);
        counts.set(kind, (counts.get(kind) ?? 0) + 1);
    }
    return KINDS
        .filter(k => counts.has(k.kind))
        .map(k => ({ ...k, count: counts.get(k.kind)! }));
}

export function filterItems(items: FileItem[], query: string, kind: Kind | null): FileItem[] {
    const q = query.toLowerCase();
    return items.filter(item =>
        item.name.toLowerCase().includes(q) && (kind === null || kindOf(item) === kind));
}

export interface KindFilter { path: string; kind: Kind }

// The type filter belongs to the folder it was picked in. Refreshing that folder keeps it;
// loading any other folder clears it, so coming back later starts from everything too.
export function keepFilter(filter: KindFilter | null, loadedPath: string): KindFilter | null {
    return filter && filter.path === loadedPath ? filter : null;
}

export type SortKey = 'name' | 'date' | 'size' | 'type';
export type SortDir = 'asc' | 'desc';
export interface Sort { key: SortKey; dir: SortDir }

export const SORTS: { key: SortKey; label: string }[] = [
    { key: 'name', label: 'Name' },
    { key: 'date', label: 'Date' },
    { key: 'size', label: 'Size' },
    { key: 'type', label: 'Type' },
];

// Where each sort starts: names A–Z, everything else newest or largest first
const FIRST_DIR: Record<SortKey, SortDir> = { name: 'asc', date: 'desc', size: 'desc', type: 'desc' };

export const DEFAULT_SORT: Sort = { key: 'name', dir: 'asc' };

export function nextSort(current: Sort, key: SortKey): Sort {
    if (current.key === key) return { key, dir: current.dir === 'asc' ? 'desc' : 'asc' };
    return { key, dir: FIRST_DIR[key] };
}

export function parseSort(key: string | null, dir: string | null): Sort {
    const found = SORTS.find(s => s.key === key);
    if (!found) return DEFAULT_SORT;
    return { key: found.key, dir: dir === 'asc' || dir === 'desc' ? dir : FIRST_DIR[found.key] };
}

const DIR_WORDS: Record<SortKey, Record<SortDir, string>> = {
    name: { asc: 'A–Z', desc: 'Z–A' },
    date: { asc: 'oldest first', desc: 'newest first' },
    size: { asc: 'smallest first', desc: 'largest first' },
    type: { asc: 'oldest first', desc: 'newest first' },
};

export function sortLabel(sort: Sort): string {
    const label = SORTS.find(s => s.key === sort.key)!.label;
    return `${label}, ${DIR_WORDS[sort.key][sort.dir]}`;
}

// A heading (null when sorting by name, which has none) and the items under it
export interface Section { label: string | null; items: FileItem[] }

// Numbers in names count up, so IMG_2 comes before IMG_10
const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });
const byName = (a: FileItem, b: FileItem) => collator.compare(a.name, b.name);

// Start of the calendar day `days` before `now`, in seconds like mtime
function dayStart(now: Date, days: number): number {
    return new Date(now.getFullYear(), now.getMonth(), now.getDate() - days).getTime() / 1000;
}

function dateSection(mtime: number, now: Date, locale?: string): string {
    // Anything dated after today (a clock set ahead) counts as today
    if (mtime >= dayStart(now, 0)) return 'Today';
    if (mtime >= dayStart(now, 1)) return 'Yesterday';
    if (mtime >= dayStart(now, 6)) return 'Last 7 days';
    if (mtime >= dayStart(now, 29)) return 'Last 30 days';
    return new Date(mtime * 1000).toLocaleDateString(locale, { month: 'long', year: 'numeric' });
}

const MB = 1024 * 1024;

function sizeSection(size: number): string {
    if (size >= 1024 * MB) return 'Over 1 GB';
    if (size >= 100 * MB) return '100 MB – 1 GB';
    if (size >= MB) return '1 MB – 100 MB';
    return 'Under 1 MB';
}

const KIND_ORDER = KINDS.map(k => k.kind);
const KIND_LABEL = Object.fromEntries(KINDS.map(k => [k.kind, k.label])) as Record<Kind, string>;

export function arrange(items: FileItem[], sort: Sort, now: Date, locale?: string): Section[] {
    const sign = sort.dir === 'asc' ? 1 : -1;
    const kinds = new Map(items.map(i => [i, kindOf(i)]));
    const kindRank = (i: FileItem) => KIND_ORDER.indexOf(kinds.get(i)!);
    const byDate = (a: FileItem, b: FileItem) => (a.mtime - b.mtime) * sign || byName(a, b);

    // Folders stay on top. The server's size for a folder means nothing, so size sorts them by name.
    const folders = items.filter(i => i.is_dir).sort(
        sort.key === 'name' ? (a, b) => byName(a, b) * sign
            : sort.key === 'size' ? byName
                : byDate);

    const files = items.filter(i => !i.is_dir).sort({
        name: (a: FileItem, b: FileItem) => byName(a, b) * sign,
        date: byDate,
        size: (a: FileItem, b: FileItem) => (a.size - b.size) * sign || byName(a, b),
        // Sections in a fixed order, then newest (or oldest) first inside each
        type: (a: FileItem, b: FileItem) =>
            kindRank(a) - kindRank(b) || byDate(a, b),
    }[sort.key]);

    if (sort.key === 'name') {
        return items.length ? [{ label: null, items: [...folders, ...files] }] : [];
    }

    const sectionOf = {
        date: (i: FileItem) => dateSection(i.mtime, now, locale),
        size: (i: FileItem) => sizeSection(i.size),
        type: (i: FileItem) => KIND_LABEL[kinds.get(i)!],
    }[sort.key];

    // Files are already in order, so each new label starts the next section
    const fileSections: Section[] = [];
    for (const file of files) {
        const label = sectionOf(file);
        const last = fileSections[fileSections.length - 1];
        if (last && last.label === label) last.items.push(file);
        else fileSections.push({ label, items: [file] });
    }
    return folders.length ? [{ label: 'Folders', items: folders }, ...fileSections] : fileSections;
}

// The date under a thumbnail: Today, Yesterday, or a short date
export function shortDate(mtime: number, now: Date, locale?: string): string {
    if (mtime >= dayStart(now, 0)) return 'Today';
    if (mtime >= dayStart(now, 1)) return 'Yesterday';
    const date = new Date(mtime * 1000);
    return date.toLocaleDateString(locale, {
        month: 'short',
        day: 'numeric',
        year: date.getFullYear() === now.getFullYear() ? undefined : 'numeric',
    });
}
