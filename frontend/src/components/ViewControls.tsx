import React from 'react';
import { ArrowDown, ArrowUp } from 'lucide-react';
import { clsx } from 'clsx';
import { SORTS, sortLabel } from '../arrange';
import type { Kind, Sort, SortKey } from '../arrange';

interface ViewControlsProps {
    kinds: { kind: Kind; label: string; count: number }[];
    total: number;
    activeKind: Kind | null;
    onKind: (kind: Kind | null) => void;
    sort: Sort;
    onSort: (key: SortKey) => void;
}

// The type chips and the sort tabs under the header. Every change is one tap.
export const ViewControls: React.FC<ViewControlsProps> = ({ kinds, total, activeKind, onKind, sort, onSort }) => {
    const chip = (key: string, label: string, count: number, active: boolean, onClick: () => void) => (
        <button
            key={key}
            onClick={onClick}
            aria-pressed={active}
            className={clsx(
                "flex-shrink-0 px-3 py-1.5 rounded-full border text-sm whitespace-nowrap transition-colors",
                active
                    ? "bg-blue-600 border-blue-600 text-white"
                    : "bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800"
            )}
        >
            {label}
            <span className="ml-1.5 text-xs opacity-60">{count}</span>
        </button>
    );

    return (
        <div className="max-w-7xl mx-auto mt-3 flex flex-col gap-2 md:flex-row md:items-center md:gap-4">
            {/* A folder with only one kind of file gets no chips */}
            {kinds.length > 1 && (
                <div className="flex gap-2 overflow-x-auto -mx-4 px-4 md:mx-0 md:px-0 md:flex-1 md:min-w-0 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                    {chip('all', 'All', total, activeKind === null, () => onKind(null))}
                    {kinds.map(k => chip(k.kind, k.label, k.count, activeKind === k.kind, () => onKind(k.kind)))}
                </div>
            )}

            <div
                role="group"
                aria-label="Sort by"
                className="flex md:ml-auto md:w-80 flex-shrink-0 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden"
            >
                {SORTS.map(({ key, label }) => {
                    const active = sort.key === key;
                    const Arrow = sort.dir === 'asc' ? ArrowUp : ArrowDown;
                    return (
                        <button
                            key={key}
                            onClick={() => onSort(key)}
                            aria-pressed={active}
                            aria-label={active ? `${sortLabel(sort)}. Tap to reverse` : `Sort by ${label.toLowerCase()}`}
                            className={clsx(
                                "flex-1 flex items-center justify-center gap-1 py-1.5 text-sm border-r last:border-r-0 border-gray-200 dark:border-gray-700 transition-colors",
                                active
                                    ? "bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 font-semibold"
                                    : "text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
                            )}
                        >
                            {label}
                            {active && <Arrow size={14} aria-hidden="true" />}
                        </button>
                    );
                })}
            </div>
        </div>
    );
};
