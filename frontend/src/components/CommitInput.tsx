import { useEffect, useRef, useState } from "react";
import type { InputHTMLAttributes } from "react";

type CommitInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "defaultValue" | "onChange" | "onBlur"> & {
  value: string;
  onCommit: (value: string) => Promise<boolean | void> | boolean | void;
};

// Keep a draft while typing; synchronize remote updates only outside editing.
export function CommitInput({ value, onCommit, readOnly, onKeyDown, ...props }: CommitInputProps) {
  const [draft, setDraft] = useState(value);
  const focused = useRef(false);
  const latestValue = useRef(value);
  latestValue.current = value;
  useEffect(() => {
    if (!focused.current || readOnly) setDraft(value);
  }, [value, readOnly]);

  return <input {...props} value={draft} readOnly={readOnly}
    onKeyDown={(event) => {
      onKeyDown?.(event);
      if (event.key === "Enter" && !event.nativeEvent.isComposing && !event.defaultPrevented) {
        event.preventDefault();
        event.stopPropagation();
        event.currentTarget.blur();
      }
    }}
    onFocus={() => { focused.current = true; }}
    onChange={(event) => setDraft(event.target.value)}
    onBlur={async () => {
      focused.current = false;
      if (readOnly || draft === latestValue.current) { setDraft(latestValue.current); return; }
      try {
        const accepted = await onCommit(draft);
        if (accepted === false && !focused.current) setDraft(latestValue.current);
      } catch {
        if (!focused.current) setDraft(latestValue.current);
      }
    }} />;
}
