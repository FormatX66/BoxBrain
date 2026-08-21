# Contributing to BoxBrain and Aurum

Thanks for helping. Contributions can be code, testing, research, documentation, hardware observations, bug reports, or workflow ideas.

For Aurum specifically, begin at [Projects/Aurum/START_HERE.md](Projects/Aurum/START_HERE.md).
For the contributor build path and expected validation evidence, use the
[Contributor build guide](CONTRIBUTOR_BUILD.md).

## Beginner path

1. Use the **Join the Aurum helper crew** issue form.
2. Describe what kind of help you want to provide.
3. Work through a small, reviewable task.
4. Report results in an issue, or submit a pull request if you changed repository files.

You do not need direct write access to the repository. Public contributors can use issues and fork-based pull requests.

## Contribution lanes

- **Tester:** reproduce behavior and report exact steps and results.
- **Windows helper:** verify Windows setup, scripts, UI, and documentation on an authorized machine.
- **Pi / hardware helper:** verify Raspberry Pi and supported hardware behavior on equipment you own or are authorized to test.
- **Documentation helper:** improve clarity, examples, spelling, organization, or beginner instructions.
- **Research helper:** investigate technical questions and include reliable sources.
- **UI / workflow helper:** propose simpler flows, labels, wording, and user interactions.
- **Developer:** fix bugs, add tests, improve automation, or implement scoped features.

## Keep changes small

Prefer one focused change per pull request. Explain:

- what you changed,
- why you changed it,
- how you checked it,
- what remains uncertain.

Small changes are easier to review, test, compare, and safely merge.

## Testing

Use the most relevant local validation for the area you changed. The repository's main validation entry point is:

```powershell
.\installer\validate-project.ps1
```

For a production web build as well:

```powershell
.\installer\validate-project.ps1 -Mode Full
```

If you cannot run a test, say so in the pull request instead of guessing.

## Safety and privacy

- Do not commit or post passwords, API keys, tokens, Wi-Fi credentials, private keys, personal files, or sensitive logs.
- Redact screenshots before uploading them.
- Test only systems, accounts, networks, and hardware that you own or are explicitly authorized to use.
- Do not weaken safety gates, approval requirements, secret handling, or audit behavior just to make a test pass.
- Do not run untrusted code with elevated privileges.

## Pull requests

GitHub will automatically show the repository pull request checklist. Complete it in plain language. A maintainer can ask for changes before anything is merged.

## Unsure what to do?

Use the Aurum helper form and choose **I am not sure — give me something easy**. No coding experience is required.
