"use client";

import { useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { JobCard } from "./job-card";

type Job = {
  id: string;
  title: string;
  company: string;
  location: string | null;
  remote_type: string | null;
  salary_min_usd: number | null;
  salary_max_usd: number | null;
  category: string | null;
  source_url: string;
  published_at: string | null;
};

export function JobGrid({ initialJobs }: { initialJobs: Job[] }) {
  const parentRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: initialJobs.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 140,
    overscan: 5,
  });

  return (
    <div
      ref={parentRef}
      className="h-[800px] overflow-auto rounded-lg border border-neutral-800"
    >
      <div
        style={{
          height: `${virtualizer.getTotalSize()}px`,
          width: "100%",
          position: "relative",
        }}
      >
        {virtualizer.getVirtualItems().map((item) => {
          const job = initialJobs[item.index];
          return (
            <div
              key={job.id}
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                height: `${item.size}px`,
                transform: `translateY(${item.start}px)`,
              }}
              className="border-b border-neutral-800 p-4 hover:bg-neutral-900"
            >
              <JobCard job={job} />
            </div>
          );
        })}
      </div>
    </div>
  );
}
