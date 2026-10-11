import { useRef, useState } from "react";
import { readPickedFiles, type PickedFiles } from "../lib/projectFiles";

/** Pick individual files or a whole folder; only source files and manifests are kept, in the browser. */
export function FilePicker({ onPicked, disabled }: { onPicked: (picked: PickedFiles) => void; disabled?: boolean }) {
  const files = useRef<HTMLInputElement>(null);
  const folder = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);

  const handle = async (list: FileList | null) => {
    if (!list || !list.length) return;
    onPicked(await readPickedFiles(list));
  };

  return (
    <div
      className={`dropzone ${drag ? "drag" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        void handle(e.dataTransfer.files);
      }}
    >
      <span className="ink2">Drop files here, or</span>
      <button type="button" className="btn sm" disabled={disabled} onClick={() => files.current?.click()}>
        Choose files
      </button>
      <button type="button" className="btn sm" disabled={disabled} onClick={() => folder.current?.click()}>
        Choose a folder
      </button>
      <span className="small muted">Only .py / .js / .ts sources and dependency manifests are uploaded. Everything else is ignored in your browser.</span>
      <input ref={files} type="file" multiple hidden onChange={(e) => void handle(e.target.files).then(() => (e.target.value = ""))} />
      <input
        ref={(el) => {
          folder.current = el;
          if (el) el.setAttribute("webkitdirectory", "");
        }}
        type="file"
        multiple
        hidden
        onChange={(e) => void handle(e.target.files).then(() => (e.target.value = ""))}
      />
    </div>
  );
}
