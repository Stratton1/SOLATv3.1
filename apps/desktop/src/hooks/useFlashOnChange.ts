/**
 * Hook that applies a flash CSS class when a numeric value changes.
 *
 * Usage:
 *   const flashClass = useFlashOnChange(value);
 *   <span className={flashClass}>{value}</span>
 *
 * Adds "flash-green" when value increases, "flash-red" when it decreases.
 * Class is removed after 600ms.
 */

import { useEffect, useRef, useState } from "react";

export function useFlashOnChange(value: number | null | undefined): string {
  const prevRef = useRef<number | null | undefined>(value);
  const [flashClass, setFlashClass] = useState("");

  useEffect(() => {
    const prev = prevRef.current;
    prevRef.current = value;

    if (prev == null || value == null) return;
    if (value === prev) return;

    const cls = value > prev ? "flash-green" : "flash-red";
    setFlashClass(cls);

    const timer = setTimeout(() => setFlashClass(""), 600);
    return () => clearTimeout(timer);
  }, [value]);

  return flashClass;
}
