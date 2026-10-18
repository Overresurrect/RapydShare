// Which viewer a file opens in, kept apart from React so it can be tested.
import type { FileItem } from './types';

export type PreviewKind = 'image' | 'video' | 'pdf' | 'text' | 'none';

const TEXT_EXTENSIONS = ['.txt', '.md', '.py', '.js'];

export function previewKind(item: Pick<FileItem, 'name' | 'mime' | 'type'>): PreviewKind {
    // The server sends SVG as plain text (it can hold script), so it can't show in an <img>
    if (item.mime === 'image/svg+xml' || item.name.toLowerCase().endsWith('.svg')) return 'text';
    if (item.type === 'image') return 'image';
    if (item.type === 'video') return 'video';
    if (item.mime === 'application/pdf') return 'pdf';
    if (item.mime?.startsWith('text/') || TEXT_EXTENSIONS.some(ext => item.name.endsWith(ext))) return 'text';
    return 'none';
}
