/** Version und Commit des laufenden Baus.
 *
 * Beide werden beim Bauen des Images gesetzt (siehe Dockerfile). Ohne diese
 * Angabe laesst sich einem gezogenen ":latest"-Image nicht ansehen, ob es
 * tatsaechlich einen neuen Stand enthaelt oder noch der alte ist.
 */
export function appVersion(): string {
  const version = import.meta.env.VITE_APP_VERSION || "0.0.0-dev";
  const sha = import.meta.env.VITE_GIT_SHA || "dev";
  return `v${version} · ${sha}`;
}
