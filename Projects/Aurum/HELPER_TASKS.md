# Aurum Helper Starter Tasks

This page gives new contributors useful things they can do immediately. Pick the smallest task that matches your interests.

## Easiest first task

Read [START_HERE.md](START_HERE.md) and the first section of the repository [README](../../README.md). Then add a comment to your helper issue answering:

1. What made sense immediately?
2. What was confusing?
3. What is one sentence or step you would rewrite?

That is a real contribution. Clear instructions are part of the product.

## Documentation helper

Choose one Aurum or BoxBrain document and find one of these:

- a missing step,
- an unexplained acronym,
- a confusing sentence,
- a broken or unclear link,
- a place where a screenshot or example would help.

Report it in your helper issue. If you are comfortable editing on GitHub, use the web editor and submit the change as a pull request.

## Windows tester

Use only a Windows computer you own or are explicitly authorized to test.

Start by checking that the written setup steps match what a normal Windows user actually sees. Record:

- Windows version,
- which documented step you tried,
- expected result,
- actual result,
- exact error text if one appears.

Do not upload credentials, tokens, personal paths, Wi-Fi secrets, or screenshots containing private information.

## Raspberry Pi / hardware tester

Use only hardware and networks you own or are explicitly authorized to test.

Verify one documented connection or setup step at a time. Report the Pi model, OS version, the single step tested, and the observed result. Redact network names, addresses, keys, and credentials when they are private.

## Research helper

Pick a technical question mentioned in an Aurum issue or document. Find two reliable sources, summarize where they agree or disagree, and post the links plus a short conclusion in your helper issue.

Prefer primary documentation, standards, vendor documentation, or original research when available.

## UI / workflow helper

Pretend you are opening Aurum for the first time. Identify one place where a normal person would not know what to do next. Describe:

- what you expected,
- what the current wording or flow suggests,
- the simplest change that would make the next action obvious.

A sketch or screenshot is optional. Redact personal information first.

## Coding helper

Pick one narrowly scoped issue or improvement. Keep the first pull request small.

Before submitting, run the most relevant tests. The repository-wide local validation entry point is:

```powershell
.\installer\validate-project.ps1
```

For the production web build too:

```powershell
.\installer\validate-project.ps1 -Mode Full
```

If you cannot run a test, state that clearly in the pull request.

## Pull request reviewer

Read one open pull request and check only what you can verify. Useful review comments include:

- a test that appears missing,
- a confusing explanation,
- an edge case,
- a safety or privacy concern,
- confirmation that a documented step worked for you.

You do not need to approve code you do not understand.

## Finished your first task?

Post the result in your helper issue. If you changed repository files, submit a pull request. The GitHub automation and pull request template will guide the handoff to review.
