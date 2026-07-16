import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Check, ChevronDown, Search, X } from "lucide-react";

import { matchesSearch } from "./search";

export interface SearchableSelectOption {
  value: string;
  label: string;
  group?: string;
  searchText?: string;
  fixed?: boolean;
}

interface SearchableSelectProps {
  value: string;
  options: SearchableSelectOption[];
  onChange: (value: string) => void;
  ariaLabel: string;
  placeholder?: string;
  searchPlaceholder?: string;
  emptyMessage?: string;
  query?: string;
  onQueryChange?: (query: string) => void;
  loading?: boolean;
  statusText?: string;
  disabled?: boolean;
}

export function SearchableSelect({
  value,
  options,
  onChange,
  ariaLabel,
  placeholder = "選択してください",
  searchPlaceholder = "候補を検索",
  emptyMessage = "一致する候補はありません。",
  query,
  onQueryChange,
  loading = false,
  statusText = "",
  disabled = false,
}: SearchableSelectProps) {
  const [open, setOpen] = useState(false);
  const [localQuery, setLocalQuery] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const listboxId = useId();
  const activeQuery = query ?? localQuery;
  const selected = options.find((option) => option.value === value);
  const visibleOptions = useMemo(() => options.filter((option) => (
    option.fixed
    || option.value === value
    || matchesSearch(activeQuery, [option.label, option.value, option.group, option.searchText])
  )), [activeQuery, options, value]);
  const groups = useMemo(() => {
    const result = new Map<string, SearchableSelectOption[]>();
    visibleOptions.forEach((option) => {
      const group = option.group ?? "";
      result.set(group, [...(result.get(group) ?? []), option]);
    });
    return [...result.entries()];
  }, [visibleOptions]);

  const changeQuery = (nextQuery: string) => {
    if (onQueryChange) onQueryChange(nextQuery);
    else setLocalQuery(nextQuery);
  };
  const close = () => {
    setOpen(false);
    changeQuery("");
  };

  useEffect(() => {
    if (!open) return undefined;
    const handleOutside = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) close();
    };
    document.addEventListener("pointerdown", handleOutside);
    window.requestAnimationFrame(() => searchRef.current?.focus());
    return () => document.removeEventListener("pointerdown", handleOutside);
  }, [open]);

  const openWithKeyboard = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== "ArrowDown" && event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    setOpen(true);
  };
  const focusFirstOption = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== "ArrowDown") return;
    event.preventDefault();
    rootRef.current?.querySelector<HTMLButtonElement>("[data-searchable-option]")?.focus();
  };
  const selectOption = (option: SearchableSelectOption) => {
    onChange(option.value);
    close();
  };

  return (
    <div className={`searchable-select${open ? " open" : ""}`} ref={rootRef} data-searchable-select>
      <button
        type="button"
        className="searchable-select-control"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={openWithKeyboard}
      >
        <span className={selected ? "" : "placeholder"}>{selected?.label ?? placeholder}</span>
        <ChevronDown size={15} aria-hidden="true" />
      </button>
      {open && (
        <div className="searchable-select-popover">
          <label className="searchable-select-search">
            <Search size={14} aria-hidden="true" />
            <input
              ref={searchRef}
              type="search"
              value={activeQuery}
              onChange={(event) => changeQuery(event.target.value)}
              onKeyDown={focusFirstOption}
              placeholder={searchPlaceholder}
              aria-label={`${ariaLabel}の候補を検索`}
              autoComplete="off"
            />
            {activeQuery && <button type="button" onClick={() => changeQuery("")} title="検索をクリア"><X size={13} /></button>}
          </label>
          {(loading || statusText) && <p className="searchable-select-status" role="status">{loading ? "検索しています..." : statusText}</p>}
          <div className="searchable-select-options" id={listboxId} role="listbox" aria-label={`${ariaLabel}の候補`}>
            {!loading && groups.map(([group, groupOptions]) => (
              <div className="searchable-select-group" key={group || "default"} role="group" aria-label={group || undefined}>
                {group && <span className="searchable-select-group-label">{group}</span>}
                {groupOptions.map((option) => (
                  <button
                    type="button"
                    role="option"
                    aria-selected={option.value === value}
                    data-searchable-option
                    data-value={option.value}
                    key={`${group}:${option.value}`}
                    onClick={() => selectOption(option)}
                    onKeyDown={(event) => {
                      if (event.key === "Escape") close();
                    }}
                  >
                    <span>{option.label}</span>
                    {option.value === value && <Check size={14} aria-hidden="true" />}
                  </button>
                ))}
              </div>
            ))}
            {!loading && visibleOptions.length === 0 && <p className="searchable-select-empty">{emptyMessage}</p>}
          </div>
        </div>
      )}
    </div>
  );
}
