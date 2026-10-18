import React, { useEffect, useRef, useState } from 'react';
import { KeyRound } from 'lucide-react';
import { clsx } from 'clsx';
import {
    CODE_LENGTH,
    EMPTY_BOXES,
    applyInput,
    backspace,
    isComplete,
    retryAfterSeconds,
} from '../codeInput';
import type { BoxUpdate } from '../codeInput';

interface CodeEntryProps {
    /** Resolves to true once the app has taken over from the form. */
    onSignedIn: () => Promise<boolean>;
}

const GROUPS = [[0, 1, 2], [3, 4, 5]];

export const CodeEntry: React.FC<CodeEntryProps> = ({ onSignedIn }) => {
    const [boxes, setBoxes] = useState<string[]>(EMPTY_BOXES);
    const [busy, setBusy] = useState(false);
    const [shaking, setShaking] = useState(false);
    const [message, setMessage] = useState('');
    const [waitLeft, setWaitLeft] = useState(0);
    const inputs = useRef<(HTMLInputElement | null)[]>([]);
    const locked = waitLeft > 0;

    // Back to the first box on load and whenever the form opens up again
    useEffect(() => {
        if (!busy && !locked) inputs.current[0]?.focus();
    }, [busy, locked]);

    useEffect(() => {
        if (!locked) return;
        const timer = setInterval(() => setWaitLeft(left => left - 1), 1000);
        return () => clearInterval(timer);
    }, [locked]);

    const submit = async (code: string) => {
        setBusy(true);
        setMessage('');
        try {
            const res = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code }),
            });
            if (res.ok) {
                if (await onSignedIn()) return;
                // Signed in, but the app couldn't load, so the form is still showing. The code stays for a retry
                setMessage('Could not load RapydShare. Press Enter to try again.');
                setBusy(false);
                return;
            }
            setBoxes(EMPTY_BOXES);
            if (res.status === 429) {
                setWaitLeft(retryAfterSeconds(res.headers.get('Retry-After')));
            } else if (res.status === 401) {
                setMessage('That code is not right. Try again.');
                setShaking(true);
            } else {
                setMessage('Something went wrong. Try again.');
            }
        } catch {
            setBoxes(EMPTY_BOXES);
            setMessage('Could not reach RapydShare. Check your connection.');
        }
        setBusy(false);
    };

    const update = ({ boxes: next, focus }: BoxUpdate) => {
        setBoxes(next);
        inputs.current[focus]?.focus();
        if (isComplete(next)) submit(next.join(''));
    };

    const handleKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Backspace') {
            e.preventDefault();
            update(backspace(boxes, index));
        } else if (e.key === 'ArrowLeft') {
            e.preventDefault();
            inputs.current[Math.max(index - 1, 0)]?.focus();
        } else if (e.key === 'ArrowRight') {
            e.preventDefault();
            inputs.current[Math.min(index + 1, CODE_LENGTH - 1)]?.focus();
        } else if (e.key === 'Enter') {
            // A form with several boxes and no submit button doesn't submit on Enter by itself
            handleSubmit(e);
        }
    };

    const handlePaste = (index: number, e: React.ClipboardEvent<HTMLInputElement>) => {
        e.preventDefault();
        update(applyInput(boxes, index, e.clipboardData.getData('text')));
    };

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (isComplete(boxes) && !busy && !locked) submit(boxes.join(''));
    };

    return (
        <div className="min-h-screen flex items-center justify-center px-4">
            <form onSubmit={handleSubmit} className="w-full max-w-sm flex flex-col items-center gap-6 text-center">
                <KeyRound size={40} className="text-blue-500" />
                <h1 className="text-xl font-bold text-gray-800 dark:text-gray-100">
                    Enter the code shown in RapydShare
                </h1>

                <div className="flex w-full items-center justify-center gap-4" role="group" aria-label="Access code">
                    {GROUPS.map((group, g) => (
                        <div key={g} className="flex min-w-0 flex-1 gap-1.5">
                            {group.map(i => (
                                <input
                                    key={i}
                                    ref={el => { inputs.current[i] = el; }}
                                    value={boxes[i]}
                                    onChange={e => update(applyInput(boxes, i, e.target.value))}
                                    onKeyDown={e => handleKeyDown(i, e)}
                                    onPaste={e => handlePaste(i, e)}
                                    onFocus={e => e.target.select()}
                                    onAnimationEnd={() => setShaking(false)}
                                    disabled={busy || locked}
                                    aria-label={`Character ${i + 1} of ${CODE_LENGTH}`}
                                    type="text"
                                    autoCapitalize="characters"
                                    autoCorrect="off"
                                    spellCheck={false}
                                    autoComplete={i === 0 ? 'one-time-code' : 'off'}
                                    className={clsx(
                                        'w-0 min-w-0 flex-1 h-14 text-center text-2xl font-mono font-bold uppercase rounded-lg',
                                        'bg-gray-100 dark:bg-gray-800 border-2 border-transparent focus:border-blue-500 outline-none',
                                        'disabled:opacity-50 transition-colors',
                                        shaking && 'shake'
                                    )}
                                />
                            ))}
                        </div>
                    ))}
                </div>

                <p role="alert" className="min-h-[1.5rem] text-sm text-red-600 dark:text-red-400">
                    {locked ? `Too many tries — try again in ${waitLeft} s` : message}
                </p>
            </form>
        </div>
    );
};
