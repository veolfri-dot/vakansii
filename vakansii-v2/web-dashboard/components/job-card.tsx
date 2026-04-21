import { Briefcase, MapPin, DollarSign, ExternalLink } from "lucide-react";

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

export function JobCard({ job }: { job: Job }) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-neutral-100">{job.title}</h3>
        <a
          href={job.source_url}
          target="_blank"
          rel="noreferrer"
          className="text-neutral-400 hover:text-white"
        >
          <ExternalLink size={16} />
        </a>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-sm text-neutral-400">
        <span className="flex items-center gap-1">
          <Briefcase size={14} /> {job.company}
        </span>
        <span className="flex items-center gap-1">
          <MapPin size={14} /> {job.location || "Remote"}
        </span>
        {job.salary_min_usd && (
          <span className="flex items-center gap-1">
            <DollarSign size={14} /> ${job.salary_min_usd.toLocaleString()}
            {job.salary_max_usd
              ? ` — $${job.salary_max_usd.toLocaleString()}`
              : ""}
          </span>
        )}
      </div>
      <div className="mt-1 text-xs text-neutral-500">
        {job.category} • {job.remote_type}
      </div>
    </div>
  );
}
