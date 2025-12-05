import React, { useState } from 'react';
import type { FileItem } from '../types';
import { X, Download, FileText, AlertCircle } from 'lucide-react';

interface PreviewModalProps {
    item: FileItem;
    onClose: () => void;
    onDownload: (item: FileItem) => void;
}

export const PreviewModal: React.FC<PreviewModalProps> = ({ item, onClose, onDownload }) => {
    const fileUrl = `/api/view?path=${encodeURIComponent(item.path)}`;
    const [error, setError] = useState(false);

    // Determine what kind of preview to show
    const renderContent = () => {
        if (error) {
            return (
                <div className="flex flex-col items-center justify-center text-white h-64">
                    <AlertCircle className="w-12 h-12 mb-2 text-red-400" />
                    <p>Preview failed to load.</p>
                </div>
            );
        }

        if (item.type === 'image') {
            return <img src={fileUrl} className="max-w-full max-h-[85vh] object-contain rounded-lg shadow-2xl" onError={() => setError(true)} />;
        }
        
        if (item.type === 'video') {
            return <video src={fileUrl} controls autoPlay className="max-w-full max-h-[85vh] rounded-lg shadow-2xl bg-black" onError={() => setError(true)} />;
        }

        // PDF Support
        if (item.mime === 'application/pdf') {
            return (
                <iframe 
                    src={fileUrl} 
                    className="w-full h-[85vh] bg-white rounded-lg" 
                    title="PDF Viewer"
                />
            );
        }

        // Text/Code files (Basic support via iframe)
        if (item.mime?.startsWith('text/') || item.name.endsWith('.txt') || item.name.endsWith('.md') || item.name.endsWith('.py') || item.name.endsWith('.js')) {
             return (
                <iframe 
                    src={fileUrl} 
                    className="w-full h-[85vh] bg-white rounded-lg border-none" 
                    title="Text Viewer"
                />
            );
        }

        // Fallback for non-previewable files
        return (
            <div className="flex flex-col items-center justify-center bg-gray-800 p-10 rounded-xl text-center">
                <FileText className="w-16 h-16 text-gray-400 mb-4" />
                <h3 className="text-xl font-bold text-white mb-2">{item.name}</h3>
                <p className="text-gray-400 mb-6">No preview available for this file type.</p>
                <button 
                    onClick={() => onDownload(item)}
                    className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg font-medium transition-colors flex items-center gap-2"
                >
                    <Download size={18} /> Download to View
                </button>
            </div>
        );
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/95 backdrop-blur-sm p-4 animate-in fade-in duration-200" onClick={onClose}>
            {/* Close Button */}
            <button onClick={onClose} className="absolute top-4 right-4 p-2 bg-gray-800/50 hover:bg-gray-700 text-white rounded-full transition-colors z-50">
                <X size={24} />
            </button>

            {/* Top Bar for Download */}
            <div className="absolute top-4 left-4 right-16 flex justify-center pointer-events-none">
                 <div className="bg-gray-900/80 backdrop-blur px-4 py-2 rounded-full flex items-center gap-4 pointer-events-auto border border-white/10">
                    <span className="text-white text-sm font-medium truncate max-w-[200px] md:max-w-md">{item.name}</span>
                    <div className="h-4 w-[1px] bg-white/20"></div>
                    <button onClick={() => onDownload(item)} className="text-blue-400 hover:text-blue-300 transition-colors">
                        <Download size={18} />
                    </button>
                 </div>
            </div>

            <div className="w-full max-w-6xl flex items-center justify-center" onClick={(e) => e.stopPropagation()}>
                {renderContent()}
            </div>
        </div>
    );
};