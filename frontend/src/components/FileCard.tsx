import React from 'react';
import type { FileItem } from '../types';
// FIX: Removed 'Image as ImageIcon' from imports
import { Folder, FileText, Film, Download } from 'lucide-react';
import { clsx } from 'clsx';

interface FileCardProps {
    item: FileItem;
    viewMode: 'grid' | 'list';
    onClick: (item: FileItem) => void;
    onDownload: (item: FileItem, e: React.MouseEvent) => void;
}

export const FileCard: React.FC<FileCardProps> = ({ item, viewMode, onClick, onDownload }) => {
    
    const formatSize = (bytes: number) => {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    };

    const getThumbUrl = (path: string) => `/api/thumb?path=${encodeURIComponent(path)}`;

    const renderIcon = () => {
        if (item.is_dir) return <Folder className="w-full h-full text-yellow-400 fill-yellow-400" />;
        if (['image', 'video'].includes(item.type)) {
            return (
                <img 
                    src={getThumbUrl(item.path)} 
                    alt={item.name}
                    loading="lazy"
                    className="w-full h-full object-cover"
                />
            );
        }
        return <FileText className="w-12 h-12 text-gray-400" />;
    };

    if (viewMode === 'list') {
        return (
            <div 
                onClick={() => onClick(item)}
                className="group flex items-center p-3 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl hover:shadow-md transition-all cursor-pointer active:scale-[0.99]"
            >
                <div className="w-10 h-10 flex-shrink-0 mr-4 flex items-center justify-center bg-gray-100 dark:bg-gray-800 rounded-lg overflow-hidden">
                    {item.is_dir ? <Folder className="w-6 h-6 text-yellow-400 fill-yellow-400" /> : renderIcon()}
                </div>
                <div className="flex-grow min-w-0">
                    <h3 className="text-sm font-medium truncate group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                        {item.name}
                    </h3>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                        {item.is_dir ? 'Folder' : formatSize(item.size)} • {new Date(item.mtime * 1000).toLocaleDateString()}
                    </p>
                </div>
                <button 
                    onClick={(e) => onDownload(item, e)}
                    className="p-2 text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full transition-colors"
                >
                    <Download size={18} />
                </button>
            </div>
        );
    }

    return (
        <div 
            onClick={() => onClick(item)}
            className="group bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden hover:shadow-lg transition-all cursor-pointer flex flex-col active:scale-95"
        >
            <div className="aspect-[5/4] bg-gray-100 dark:bg-gray-800 relative flex items-center justify-center overflow-hidden">
                <div className={clsx("w-full h-full flex items-center justify-center", item.is_dir ? "p-8" : "p-0")}>
                    {renderIcon()}
                </div>
                
                {item.type === 'video' && (
                    <div className="absolute inset-0 bg-black/20 flex items-center justify-center">
                        <Film className="text-white drop-shadow-lg w-10 h-10 opacity-90" />
                    </div>
                )}
            </div>

            <div className="p-3 flex flex-col flex-grow">
                <h3 className="text-sm font-medium text-gray-700 dark:text-gray-200 line-clamp-2 break-words leading-snug mb-2 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                    {item.name}
                </h3>
                <div className="mt-auto flex justify-between items-center pt-2 border-t border-gray-100 dark:border-gray-800">
                    <span className="text-[10px] text-gray-500 font-medium">
                        {item.is_dir ? '' : formatSize(item.size)}
                    </span>
                    <button 
                        onClick={(e) => onDownload(item, e)}
                        className="p-1.5 text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full transition-colors"
                    >
                        <Download size={16} />
                    </button>
                </div>
            </div>
        </div>
    );
};