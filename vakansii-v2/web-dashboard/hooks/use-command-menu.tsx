"use client";

import { useEffect, useState } from "react";
import { useJobsStore } from "@/lib/store";

export function useCommandMenu() {
  const [open, setOpen] = useState(false);
  const jobs = useJobsStore((s) => s.jobs);

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((open) => !open);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  const onSelect = (url: string) => {
    setOpen(false);
    window.open(url, "_blank");
  };

  return { open, setOpen, jobs, onSelect };
}
