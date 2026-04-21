"use client";

import { Command } from "cmdk";
import { useCommandMenu } from "@/hooks/use-command-menu";
import { Search } from "lucide-react";

export function CommandMenu() {
  const { open, setOpen, jobs, onSelect } = useCommandMenu();

  return (
    <Command.Dialog
      open={open}
      onOpenChange={setOpen}
      label="Глобальное меню команд"
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-[20vh]"
    >
      <div className="w-full max-w-xl overflow-hidden rounded-lg border border-neutral-800 bg-neutral-900 shadow-2xl">
        <div className="flex items-center border-b border-neutral-800 px-3">
          <Search className="mr-2 h-4 w-4 shrink-0 text-neutral-400" />
          <Command.Input
            placeholder="Название вакансии или компания..."
            className="h-12 w-full bg-transparent text-sm text-neutral-100 outline-none placeholder:text-neutral-500"
          />
        </div>
        <Command.List className="max-h-[300px] overflow-y-auto p-2">
          <Command.Empty className="py-6 text-center text-sm text-neutral-500">
            Ничего не найдено.
          </Command.Empty>
          {jobs.map((job) => (
            <Command.Item
              key={job.id}
              onSelect={() => onSelect(job.source_url)}
              className="cursor-pointer rounded px-2 py-1.5 text-sm text-neutral-300 hover:bg-neutral-800 hover:text-neutral-100"
            >
              {job.title}
            </Command.Item>
          ))}
        </Command.List>
      </div>
    </Command.Dialog>
  );
}
