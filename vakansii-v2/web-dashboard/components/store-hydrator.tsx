"use client";

import { useEffect } from "react";
import { useJobsStore } from "@/lib/store";

export function StoreHydrator({
  jobs,
}: {
  jobs: { id: string; title: string; source_url: string }[];
}) {
  const setJobs = useJobsStore((s) => s.setJobs);
  useEffect(() => {
    setJobs(jobs);
  }, [jobs, setJobs]);
  return null;
}
