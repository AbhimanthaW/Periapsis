# Development

Clone the shared repository when the owner provides its URL. For a local review use `git clone --no-local "/path/to/return-window" return-window-review`. Start a change from the accepted baseline with `git switch -c topic/descriptive-name`. Run the affected checks, inspect `git diff --cached`, and make scoped commits. Open a PR once the owner has set up remote collaboration. Include evidence and remaining limits in the PR template.

Integrated changes need an independent reviewer. Yumeth reviews data and producer changes. Senula reviews runtime and consumer changes. Changes crossing the pack boundary need both. Isath reviews scientific assumptions, reference frames and evidence. Abhimantha resolves architecture and integration decisions. Record each required sign-off in the PR. GitHub code-owner assignment alone does not enforce that both producer and consumer approve.

The CODEOWNERS file records the intended mapping in comments. Replace the placeholders with confirmed accounts or teams with write access before relying on automated reviewer requests. Configure branch protection and required checks once the remote exists.
