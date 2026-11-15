import React from 'react';
import { FileCode } from 'lucide-react';
import { FileRecord } from '../types';

interface FileTreeProps {
  files: FileRecord[];
  selectedFileId: string | null;
  onSelectFile: (fileId: string) => void;
}

export const FileTree: React.FC<FileTreeProps> = ({
  files,
  selectedFileId,
  onSelectFile,
}) => {
  return (
    <div className="w-80 border-r border-slate-800 bg-slate-900/30 flex flex-col shrink-0" data-testid="file-tree">
      <div className="px-4 py-3 border-b border-slate-800/80 text-xs font-semibold uppercase tracking-wider text-slate-400">
        Files ({files.length})
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {files.length === 0 ? (
          <div className="p-4 text-center text-xs text-slate-500">No files found</div>
        ) : (
          files.map((file) => {
            const isSelected = file.id === selectedFileId;
            return (
              <button
                key={file.id}
                onClick={() => onSelectFile(file.id)}
                className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-left text-xs transition-colors ${
                  isSelected
                    ? 'bg-indigo-600/20 text-indigo-300 font-medium border border-indigo-500/30'
                    : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                }`}
                data-testid={`file-item-${file.id}`}
              >
                <div className="flex items-center gap-2 overflow-hidden pr-2">
                  <FileCode className={`h-3.5 w-3.5 shrink-0 ${isSelected ? 'text-indigo-400' : 'text-slate-500'}`} />
                  <span className="truncate">{file.path}</span>
                </div>
                <span className="text-[10px] text-slate-500 shrink-0">{file.loc} L</span>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
};
