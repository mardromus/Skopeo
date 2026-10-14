import { GitHubImport } from "../components/GitHubConnect";

export function GitHubPage() {
  return (
    <main className="page narrow">
      <span className="eyebrow">Import</span>
      <h1 className="page-title">GitHub repositories</h1>
      <p className="lede ink2">
        Pick a repository to <b>investigate</b> it (eight specialist agents, red-team verification, then you can ask the agents about it), or <b>add it as a project</b> so Skopeo can watch the
        open-source libraries it depends on.
      </p>
      <GitHubImport />
    </main>
  );
}
