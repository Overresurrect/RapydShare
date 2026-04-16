export interface FileItem {
    name: string;
    path: string;
    is_dir: boolean;
    size: number;
    mtime: number;
    mime: string | null;
    type: 'folder' | 'image' | 'video' | 'file';
}

export interface UploadTask {
    id: string;
    file: File;
    progress: number;
    status: 'queued' | 'uploading' | 'done' | 'error';
    error?: string;
    xhr?: XMLHttpRequest;
}