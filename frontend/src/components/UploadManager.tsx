import React from 'react';
import type { UploadTask } from '../types';
import { X, CheckCircle2, AlertCircle, Upload as UploadIcon, XCircle } from 'lucide-react';
import { clsx } from 'clsx';

interface UploadManagerProps {
    tasks: UploadTask[];
    onDismiss: (id: string) => void;
    onCancel: (id: string) => void;
    onClearAll: () => void;
}

const formatSize = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
};

export const UploadManager: React.FC<UploadManagerProps> = ({ tasks, onDismiss, onCancel, onClearAll }) => {
    if (tasks.length === 0) return null;

    const inFlight = tasks.filter(t => t.status === 'uploading' || t.status === 'queued').length;
    const headerText = inFlight > 0
        ? `Uploading ${inFlight} file${inFlight === 1 ? '' : 's'}`
        : `${tasks.length} upload${tasks.length === 1 ? '' : 's'} complete`;

    return (
        <div
            className="fixed bottom-4 right-4 z-40 w-80 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl shadow-lg overflow-hidden"
            style={{ maxWidth: 'calc(100vw - 2rem)' }}
        >
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-800">
                <div className="flex items-center gap-2 min-w-0">
                    <UploadIcon size={16} className="text-blue-500 flex-shrink-0" />
                    <h3 className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">
                        {headerText}
                    </h3>
                </div>
                <button
                    onClick={onClearAll}
                    className="text-xs text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-100 transition-colors px-2 py-1 rounded"
                >
                    Clear
                </button>
            </div>

            <div className="max-h-64 overflow-y-auto">
                {tasks.map(task => {
                    const isDone = task.status === 'done';
                    const isError = task.status === 'error';
                    const isActive = task.status === 'uploading' || task.status === 'queued';

                    return (
                        <div
                            key={task.id}
                            className="px-4 py-3 border-b border-gray-100 dark:border-gray-800 last:border-b-0"
                        >
                            <div className="flex items-center gap-2 mb-1.5">
                                <span
                                    className="text-sm text-gray-800 dark:text-gray-100 truncate flex-grow min-w-0"
                                    title={task.file.name}
                                >
                                    {task.file.name}
                                </span>
                                {isActive ? (
                                    <button
                                        onClick={() => onCancel(task.id)}
                                        className="text-gray-400 hover:text-red-500 transition-colors flex-shrink-0"
                                        title="Cancel"
                                    >
                                        <XCircle size={16} />
                                    </button>
                                ) : (
                                    <button
                                        onClick={() => onDismiss(task.id)}
                                        className="text-gray-400 hover:text-gray-800 dark:hover:text-gray-100 transition-colors flex-shrink-0"
                                        title="Dismiss"
                                    >
                                        <X size={16} />
                                    </button>
                                )}
                            </div>

                            <div className="flex items-center gap-2">
                                <div className="flex-grow h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                                    <div
                                        className={clsx(
                                            "h-full transition-all duration-200",
                                            isError ? "bg-red-500" : isDone ? "bg-green-500" : "bg-blue-500"
                                        )}
                                        style={{ width: `${isDone ? 100 : task.progress}%` }}
                                    />
                                </div>
                                <div className="flex-shrink-0 w-10 text-right">
                                    {isDone ? (
                                        <CheckCircle2 size={16} className="text-green-500 inline" />
                                    ) : isError ? (
                                        <AlertCircle size={16} className="text-red-500 inline" />
                                    ) : (
                                        <span className="text-xs text-gray-500 dark:text-gray-400 tabular-nums">
                                            {Math.round(task.progress)}%
                                        </span>
                                    )}
                                </div>
                            </div>

                            <div className="mt-1 text-xs">
                                {isError ? (
                                    <span className="text-red-500 break-words">{task.error || 'Upload failed'}</span>
                                ) : (
                                    <span className="text-gray-500 dark:text-gray-400">
                                        {formatSize(task.file.size)}
                                    </span>
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
};
