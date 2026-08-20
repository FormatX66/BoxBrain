# Aurum Adaptive Learning & Accessibility

## North-star intent

Aurum should reduce friction for people with learning differences and disabilities without forcing them to communicate, type, read, remember, or navigate the way a conventional computer expects.

The governing principle is:

**Help the user now; help the user grow next.**

Aurum should first preserve the person's intent and keep them moving. When the user wants it, Aurum should then turn moments of friction into lightweight learning opportunities that improve confidence and skill over time.

This is not a diagnostic system and must not infer or label a medical condition from behavior. It adapts to observed interaction patterns and user preferences.

## Capability model

These are Aurum traits with stable machine semantics and user-adaptable names. Suggested canonical identities are:

- `TR8:INTENT` — infer intended meaning across imperfect typing, speech, shorthand, gestures, and incomplete commands.
- `TR8:WORDS` — assist word retrieval when the user appears to know a concept but cannot retrieve or spell the desired word.
- `TR8:LEARN` — provide optional personalized coaching based on the user's own recurring friction patterns.
- `TR8:READ` — adapt presentation, pacing, summarization, pronunciation, and reading assistance to the individual.

The user may call these Trix, apps, tools, skills, a typing coach, spell help, or anything else. Aurum owns the semantic mapping; the user owns the language.

## Intent correction, not generic autocorrect

Traditional autocorrect mainly asks whether a token resembles a dictionary word. Aurum should ask what the person most likely intended given:

- surrounding sentence and conversation context,
- the user's historical error patterns,
- phonetic similarity,
- keyboard and motor proximity,
- semantic plausibility,
- repeated substitutions,
- user-specific vocabulary and phrasing,
- current task and domain,
- confidence that the correction preserves meaning.

Suggested behavior:

- high confidence: correct unobtrusively while preserving an easy undo path;
- medium confidence: surface a lightweight suggestion;
- low confidence: leave the user's text alone;
- meaning-changing ambiguity: ask or present alternatives rather than silently rewriting intent.

Aurum must learn from rejected corrections and intentional unusual language so personalization does not flatten the user's voice.

## Friction detection

Aurum should observe the interaction process, not only the final text. Useful optional local signals include:

- repeated backspacing or retyping at the same position,
- several different partial word attempts,
- unusually long pauses in the middle of a phrase,
- repeated synonym replacement,
- phonetic attempts at an unknown spelling,
- typing a definition such as "the thing that..." instead of a word,
- abandoning or restructuring a sentence after repeated attempts,
- accepting a suggestion and immediately deleting it,
- recurring spelling or typing patterns over time.

These signals should be interpreted probabilistically. Backspace alone is not evidence of disability or confusion.

## Word-retrieval assistance

When evidence suggests the user is searching for a word rather than merely correcting a typo, Aurum can offer a small contextual set of likely words.

The ranking should consider the concept and domain rather than behaving like a generic thesaurus. For example, the best word for a vehicle vibration description may differ from the best word in a physics report even when the user's partial phrase is similar.

The assistance should remain transient and nonintrusive. Ignoring it should make it disappear, not trigger repeated prompts.

## Teaching without interruption

Normal work mode should prioritize task completion. Aurum should not turn every mistake into a lesson.

When learning is enabled, Aurum can accumulate patterns and offer short, well-timed practice such as:

- words repeatedly misspelled or searched for,
- letter sequences frequently transposed,
- typing patterns that cause recurring corrections,
- vocabulary the user repeatedly reaches for,
- reading or comprehension patterns the user explicitly wants to strengthen.

The teaching loop should become less intrusive as the user improves. A successful learning trait gradually makes itself less necessary.

## Accessibility principles

1. **Preserve dignity and agency.** Help without scolding, grading, or constantly drawing attention to mistakes.
2. **Do not diagnose.** Behavioral adaptation is not medical classification.
3. **Keep personal models private by default.** Typing history, correction patterns, reading behavior, and learning profiles should be processed locally whenever practical and treated as sensitive user state.
4. **User-controlled teaching.** Immediate intent assistance and explicit coaching are separate controls. A user may want help without lessons.
5. **Explainability on demand.** The user should be able to ask why Aurum changed or suggested something.
6. **Easy undo and correction.** The user always has the final word over their own language.
7. **Measure progress, not conformity.** Useful metrics include reduced friction, fewer unwanted corrections, improved accuracy at the user's preferred speed, words learned, and confidence—not resemblance to a generic writing style.
8. **Adapt across modalities.** The same intent model may eventually help typing, speech, reading, gesture, navigation, and other human-machine interaction.

## First real prototype

After Hopper has a stable physical graphical/input path, the first prototype should capture local keyboard-edit events in an explicitly enabled test surface and build a private interaction trace containing timing and edit structure rather than the sensitive text content whenever possible.

Milestone A — detect probable word-search episodes from repeated backspace/retype/pause patterns.

Milestone B — offer context-aware word candidates without blocking typing.

Milestone C — learn accepted/rejected suggestions and recurring user-specific error patterns.

Milestone D — add optional micro-coaching that uses the user's real recurring patterns.

Milestone E — measure whether assistance reduces friction and whether coaching reduces repeated assistance needs.

## Pitch

**Aurum does not ask people with learning differences to become better at operating a computer before the computer becomes useful to them. The computer learns how the person communicates, preserves their intent when conventional input fails, and—when invited—teaches along the way.**

The goal is not a smarter spellchecker. The goal is a continuously adapting human-computer interface that understands friction, protects the user's voice, and grows with the person.
