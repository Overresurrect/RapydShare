import { useState, useEffect, useMemo, useRef, useCallback, Fragment } from 'react';
import type { FileItem, UploadTask } from './types';
import { FileCard } from './components/FileCard';
import { PreviewModal } from './components/PreviewModal';
import { UploadManager } from './components/UploadManager';
import { CodeEntry } from './components/CodeEntry';
import { ViewControls } from './components/ViewControls';
import { uploadErrorMessage } from './uploadErrors';
import { arrange, filterItems, keepFilter, nextSort, parseSort, presentKinds, sortLabel, DEFAULT_SORT } from './arrange';
import type { Kind, KindFilter, Sort, SortKey } from './arrange';
import { ArrowLeft, Search, Moon, Sun, LayoutGrid, List, RefreshCw, FolderOpen, Upload, LogOut } from 'lucide-react';
import { clsx } from 'clsx';

function savedSort(): Sort {
  try {
    return parseSort(localStorage.getItem('sortKey'), localStorage.getItem('sortDir'));
  } catch {
    return DEFAULT_SORT;
  }
}

function App() {
  const [items, setItems] = useState<FileItem[]>([]);
  const [currentPath, setCurrentPath] = useState('');
  // Loading until the session check is done, so an empty folder doesn't flash first
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [sort, setSort] = useState<Sort>(savedSort);
  // Cleared whenever another folder loads (see keepFilter), so a folder never looks empty because of it
  const [kindFilter, setKindFilter] = useState<KindFilter | null>(null);
  // When the list was loaded, so Today and Yesterday are worked out from one moment
  const [loadedAt, setLoadedAt] = useState(0);
  const [previewItem, setPreviewItem] = useState<FileItem | null>(null);
  const [isDark, setIsDark] = useState(false);
  const [uploadEnabled, setUploadEnabled] = useState(false);
  const [requireCode, setRequireCode] = useState(false);
  const [needsCode, setNeedsCode] = useState(false);
  const [tasks, setTasks] = useState<UploadTask[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dragCounter = useRef(0);

  // --- Session ---
  // Any 401 means there's no session, so the code form takes over
  const apiFetch = useCallback(async (url: string, init?: RequestInit) => {
    const res = await fetch(url, init);
    if (res.status === 401) setNeedsCode(true);
    return res;
  }, []);

  const fetchFiles = useCallback(async (path: string) => {
    setLoading(true);
    try {
      const res = await apiFetch(`/api/files?path=${encodeURIComponent(path)}`);
      if (!res.ok) throw new Error('Failed to load');
      const data = await res.json();
      setItems(data);
      setCurrentPath(path);
      setLoadedAt(Date.now());
      setKindFilter(filter => keepFilter(filter, path));
      window.scrollTo(0, 0);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [apiFetch]);

  // True once signed in and loading the files
  const loadSession = useCallback(async () => {
    try {
      const res = await apiFetch('/api/server_info');
      if (!res.ok) throw new Error('Failed to load');
      const info = await res.json();
      setUploadEnabled(!!info.allow_upload);
      setRequireCode(!!info.require_code);
      setNeedsCode(false);
      fetchFiles('');
      return true;
    } catch (err) {
      console.error(err);
      setUploadEnabled(false);
      setLoading(false);
      return false;
    }
  }, [apiFetch, fetchFiles]);

  const handleDisconnect = async () => {
    try {
      await fetch('/api/logout', { method: 'POST' });
    } catch (err) {
      console.error(err);
    }
    setItems([]);
    setPreviewItem(null);
    setNeedsCode(true);
  };

  // --- Initialization ---
  useEffect(() => {
    // Load Preferences
    const savedTheme = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    if (savedTheme === 'dark' || (!savedTheme && prefersDark)) {
      setIsDark(true);
      document.documentElement.classList.add('dark');
    }

    const savedView = localStorage.getItem('viewMode') as 'grid' | 'list';
    if (savedView) setViewMode(savedView);

    loadSession();
  }, [loadSession]);

  // --- Actions ---
  const toggleTheme = () => {
    const newDark = !isDark;
    setIsDark(newDark);
    if (newDark) {
      document.documentElement.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('theme', 'light');
    }
  };

  const toggleView = () => {
    const newView = viewMode === 'grid' ? 'list' : 'grid';
    setViewMode(newView);
    localStorage.setItem('viewMode', newView);
  };

  const handleSort = (key: SortKey) => {
    const next = nextSort(sort, key);
    setSort(next);
    try {
      localStorage.setItem('sortKey', next.key);
      localStorage.setItem('sortDir', next.dir);
    } catch {
      // Storage can be blocked (private browsing); the sort still applies to this visit
    }
  };

  const handleNavigateUp = () => {
    if (!currentPath) return;
    const parts = currentPath.split('/');
    parts.pop();
    fetchFiles(parts.join('/'));
  };

  const handleDownload = (item: FileItem, e?: React.MouseEvent) => {
    e?.stopPropagation();
    const endpoint = item.is_dir ? '/api/download_folder' : '/api/download';
    window.location.href = `${endpoint}?path=${encodeURIComponent(item.path)}`;
  };

  const handleCardClick = (item: FileItem) => {
    if (item.is_dir) {
      fetchFiles(item.path);
    } else {
      setPreviewItem(item);
    }
  };

  // --- Upload ---
  const updateTask = useCallback((id: string, patch: Partial<UploadTask>) => {
    setTasks(prev => prev.map(t => t.id === id ? { ...t, ...patch } : t));
  }, []);

  const startUpload = useCallback((task: UploadTask) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload');
    xhr.setRequestHeader('X-File-Name', encodeURIComponent(task.file.name));
    xhr.setRequestHeader('Content-Type', 'application/octet-stream');

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable) {
        const pct = (e.loaded / e.total) * 100;
        updateTask(task.id, { status: 'uploading', progress: pct });
      }
    });

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        updateTask(task.id, { status: 'done', progress: 100 });
        fetchFiles(currentPath);
      } else {
        if (xhr.status === 401) setNeedsCode(true);
        updateTask(task.id, { status: 'error', error: uploadErrorMessage(xhr.status) });
      }
    });

    xhr.addEventListener('error', () => {
      updateTask(task.id, { status: 'error', error: 'Network error' });
    });

    xhr.addEventListener('abort', () => {
      updateTask(task.id, { status: 'error', error: 'Cancelled' });
    });

    xhr.send(task.file);
    updateTask(task.id, { xhr, status: 'uploading' });
  }, [currentPath, updateTask, fetchFiles]);

  const enqueueFiles = useCallback((files: FileList | null) => {
    if (!uploadEnabled || !files || files.length === 0) return;
    const newTasks: UploadTask[] = Array.from(files).map(file => ({
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      file,
      progress: 0,
      status: 'queued' as const,
    }));
    setTasks(prev => [...prev, ...newTasks]);
    newTasks.forEach(startUpload);
  }, [uploadEnabled, startUpload]);

  const handleFilePick = (e: React.ChangeEvent<HTMLInputElement>) => {
    enqueueFiles(e.target.files);
    e.target.value = '';
  };

  const cancelTask = useCallback((id: string) => {
    setTasks(prev => {
      const task = prev.find(t => t.id === id);
      if (task?.xhr) task.xhr.abort();
      return prev;
    });
  }, []);

  const dismissTask = useCallback((id: string) => {
    setTasks(prev => prev.filter(t => t.id !== id));
  }, []);

  const clearFinished = useCallback(() => {
    setTasks(prev => prev.filter(t => t.status === 'uploading' || t.status === 'queued'));
  }, []);

  const handleDragEnter = (e: React.DragEvent) => {
    if (!uploadEnabled) return;
    if (!e.dataTransfer.types.includes('Files')) return;
    e.preventDefault();
    dragCounter.current += 1;
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    if (!uploadEnabled) return;
    e.preventDefault();
    dragCounter.current -= 1;
    if (dragCounter.current <= 0) {
      dragCounter.current = 0;
      setIsDragging(false);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    if (!uploadEnabled) return;
    if (!e.dataTransfer.types.includes('Files')) return;
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent) => {
    if (!uploadEnabled) return;
    e.preventDefault();
    dragCounter.current = 0;
    setIsDragging(false);
    enqueueFiles(e.dataTransfer.files);
  };

  // --- Filtering, Sorting & Grouping ---
  const kinds = useMemo(() => presentKinds(items), [items]);
  const activeKind = kindFilter && kindFilter.path === currentPath && kinds.some(k => k.kind === kindFilter.kind)
    ? kindFilter.kind
    : null;
  // Tapping the active chip again goes back to everything
  const handleKind = (kind: Kind | null) =>
    setKindFilter(kind === null || kind === activeKind ? null : { path: currentPath, kind });

  const filteredItems = useMemo(
    () => filterItems(items, searchQuery, activeKind),
    [items, searchQuery, activeKind],
  );
  const sections = useMemo(
    () => arrange(filteredItems, sort, new Date(loadedAt)),
    [filteredItems, sort, loadedAt],
  );
  const showing = filteredItems.length === items.length
    ? `${items.length} ${items.length === 1 ? 'item' : 'items'}`
    : `${filteredItems.length} of ${items.length}`;

  if (needsCode) return <CodeEntry onSignedIn={loadSession} />;

  return (
    <div
      className="min-h-screen flex flex-col transition-colors duration-200"
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >

      {/* --- HEADER --- */}
      <header className="sticky top-0 z-40 bg-white/80 dark:bg-gray-900/80 backdrop-blur-md border-b border-gray-200 dark:border-gray-800 px-4 py-3">
        <div className="max-w-7xl mx-auto flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          
          {/* Breadcrumbs & Nav */}
          <div className="flex items-center gap-3 overflow-hidden">
            <button 
              onClick={handleNavigateUp} 
              disabled={!currentPath}
              className="p-2 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
            >
              <ArrowLeft size={20} />
            </button>
            <h1 className="font-bold text-lg text-gray-800 dark:text-gray-100 truncate">
               <span className="opacity-50">/ </span>
               {currentPath || 'Home'}
            </h1>
          </div>

          {/* Controls */}
          <div className="flex items-center gap-2 md:gap-3">
            <div className="relative flex-grow md:flex-grow-0">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 w-4 h-4" />
              <input 
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search files..." 
                className="w-full md:w-64 pl-9 pr-4 py-2 bg-gray-100 dark:bg-gray-800 border-none rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none transition-all"
              />
            </div>
            
            <button onClick={toggleView} className="p-2 rounded-lg text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
              {viewMode === 'grid' ? <List size={20} /> : <LayoutGrid size={20} />}
            </button>

            <button onClick={toggleTheme} className="p-2 rounded-lg text-gray-600 dark:text-yellow-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
              {isDark ? <Sun size={20} /> : <Moon size={20} />}
            </button>

            <button onClick={() => fetchFiles(currentPath)} className="p-2 rounded-lg text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30 hover:bg-blue-100 dark:hover:bg-blue-900/50 transition-colors">
              <RefreshCw size={20} className={clsx(loading && "animate-spin")} />
            </button>

            {requireCode && (
              <button
                onClick={handleDisconnect}
                title="Disconnect"
                className="flex items-center gap-2 p-2 rounded-lg text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors text-sm font-medium"
              >
                <LogOut size={20} />
                <span className="hidden sm:inline">Disconnect</span>
              </button>
            )}

            {uploadEnabled && (
              <>
                <input
                  type="file"
                  multiple
                  ref={fileInputRef}
                  onChange={handleFilePick}
                  className="hidden"
                />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors text-sm font-medium"
                >
                  <Upload size={18} />
                  <span className="hidden sm:inline">Upload</span>
                </button>
              </>
            )}
          </div>
        </div>

        {items.length > 0 && (
          <ViewControls
            kinds={kinds}
            total={items.length}
            activeKind={activeKind}
            onKind={handleKind}
            sort={sort}
            onSort={handleSort}
          />
        )}
      </header>

      {/* --- MAIN CONTENT --- */}
      <main className="flex-1 p-4 md:p-6 max-w-7xl mx-auto w-full">
        
        {loading && items.length === 0 && (
          <div className="flex justify-center pt-20">
            <RefreshCw className="animate-spin text-blue-500 w-8 h-8" />
          </div>
        )}

        {!loading && filteredItems.length === 0 && (
          <div className="flex flex-col items-center justify-center pt-20 text-gray-400">
            <FolderOpen size={64} strokeWidth={1} className="mb-4 opacity-50" />
            <p className="text-lg font-medium">No files found</p>
          </div>
        )}

        {items.length > 0 && (
          <p className="px-1 mb-3 text-xs text-gray-500 dark:text-gray-400">
            {showing} · {sortLabel(sort)}
          </p>
        )}

        <div className={clsx(
          "pb-20 transition-all",
          viewMode === 'grid'
            ? "grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3 md:gap-4"
            : "flex flex-col gap-2"
        )}>
          {sections.map((section) => (
            <Fragment key={section.label ?? 'all'}>
              {section.label && (
                <h2 className="col-span-full flex justify-between px-1 pt-4 first:pt-0 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  <span>{section.label}</span>
                  <span>{section.items.length}</span>
                </h2>
              )}
              {section.items.map((item) => (
                <FileCard
                  key={item.name}
                  item={item}
                  viewMode={viewMode}
                  showDate={sort.key === 'date' || sort.key === 'type'}
                  now={loadedAt}
                  onClick={handleCardClick}
                  onDownload={handleDownload}
                />
              ))}
            </Fragment>
          ))}
        </div>
      </main>

      {/* --- PREVIEW MODAL --- */}
      {previewItem && (
        <PreviewModal
          item={previewItem}
          onClose={() => setPreviewItem(null)}
          onDownload={handleDownload}
        />
      )}

      {/* --- DRAG OVERLAY --- */}
      {isDragging && uploadEnabled && (
        <div className="fixed inset-0 z-50 pointer-events-none bg-blue-500/20 border-4 border-dashed border-blue-500 flex items-center justify-center">
          <div className="bg-white dark:bg-gray-900 border border-blue-500 rounded-2xl px-8 py-6 shadow-xl flex flex-col items-center gap-3">
            <Upload size={40} className="text-blue-500" />
            <p className="text-lg font-semibold text-gray-800 dark:text-gray-100">
              Drop files to upload
            </p>
          </div>
        </div>
      )}

      <UploadManager
        tasks={tasks}
        onDismiss={dismissTask}
        onCancel={cancelTask}
        onClearAll={clearFinished}
      />

    </div>
  );
}

export default App;