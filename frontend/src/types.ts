export interface FileItem {
    name: string;
    path: string;
    is_dir: boolean;
    size: number;
    mtime: number;
    mime: string | null;
    type: 'folder' | 'image' | 'video' | 'file';
}