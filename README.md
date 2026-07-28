# BoxBrain

BoxBrain is the canonical knowledge and coordination repository for the
BoxBrain ecosystem. It indexes projects, architecture, decisions, agents,
prompts, handoffs, and execution plans without duplicating implementation
repositories.

## Start here

- [Repository index](Admin/RepositoryIndex.md)
- [Project index](Projects/README.md)
- [Master TODO](Admin/MasterTODO.md)
- [Roadmap](Admin/Roadmap.md)
- [Decision index](Admin/Decisions.md)
- [Change index](Admin/ChangeLog.md)
- [Session index](Admin/SessionIndex.md)

## Architecture

- [System architecture](Architecture/SystemArchitecture.md)
- [Agent architecture](Architecture/AgentArchitecture.md)
- [Knowledge and execution data flow](Architecture/DataFlow.md)
- [Integration registry](Architecture/Integrations.md)

## Operating knowledge

- [Agent role index](Agents/README.md)
- [Prompt library](PromptLibrary/README.md)
- [Templates](Templates/README.md)
- [Session handoffs](SessionHandoffs/README.md)
- [Archive policy](Archive/README.md)

## Source-of-truth rule

BoxBrain stores cross-project indexes, dependencies, decisions, and handoffs.
Project-specific code and detailed technical documentation remain in the
registered implementation repository. A document has one canonical location;
other locations link to it.

## Current state

BrainConnect is the only discovered implementation repository. The other
project entries are discovery placeholders and do not claim that source code
or separate repositories exist.

Run the repository validator from this directory:

```powershell
python .\Admin\validate_repository.py
```
