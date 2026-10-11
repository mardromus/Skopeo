import type { ProjectFileUpload } from "../services/api";

/** Files worth uploading as project context: source that may call a library, and dependency manifests. */
const SOURCE = /\.(py|js|jsx|mjs|cjs|ts|tsx|mts|cts)$/i;
const MANIFEST = /(^|\/)(requirements[^/]*\.txt|pyproject\.toml|setup\.cfg|Pipfile|package\.json)$/i;
const SKIP = /(^|\/)(node_modules|\.git|\.venv|venv|env|__pycache__|dist|build|\.next|coverage|site-packages)(\/|$)/;
export const MAX_FILE_BYTES = 400_000;
export const MAX_FILES = 400;

export interface PickedFiles {
  files: ProjectFileUpload[];
  skipped: number;
  tooLarge: string[];
}

function relPath(file: File): string {
  const rel = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
  // drop the picked folder's own name so paths read like the repository (src/app.py, not my-repo/src/app.py)
  const parts = rel.split("/");
  return parts.length > 1 && (file as File & { webkitRelativePath?: string }).webkitRelativePath ? parts.slice(1).join("/") : rel;
}

export async function readPickedFiles(list: FileList | File[]): Promise<PickedFiles> {
  const out: ProjectFileUpload[] = [];
  const tooLarge: string[] = [];
  let skipped = 0;
  for (const file of Array.from(list)) {
    const path = relPath(file);
    if (SKIP.test(path) || !(SOURCE.test(path) || MANIFEST.test(path))) {
      skipped++;
      continue;
    }
    if (file.size > MAX_FILE_BYTES) {
      tooLarge.push(path);
      continue;
    }
    if (out.length >= MAX_FILES) {
      skipped++;
      continue;
    }
    out.push({ path, content: await file.text() });
  }
  return { files: out, skipped, tooLarge };
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
