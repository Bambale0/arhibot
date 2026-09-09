# Questionnaire UX principles

The questionnaire UI is a mobile-first conversational wizard for an architectural design product.

## Interaction

- Keep one meaningful question in primary focus.
- Preserve questionnaire source wording and business rules; visual presentation must not change semantics.
- Use large touch targets for answer choices and visible selected states.
- Keep skip secondary and only show it when the source explicitly allows it.
- Keep custom input obvious and validate before continuing.
- Keep the primary action reachable near the bottom edge on mobile.
- Show selected-object progress without competing with the active question.
- Treat render review as a distinct visual state: image first, then Approve / Refine.
- Respect safe areas, keyboard use, focus-visible, and reduced-motion preferences.
- Do not preload heavy 3D/WebGL work as part of questionnaire interaction.

## Visual direction

The questionnaire should read as an architect's working sheet, not a generic SaaS card stack.

- Ground the palette in cool drafting paper, graphite, concrete-grey lines and one technical blue-green ink accent.
- Use the accent sparingly for the current stage, the selected answer and the primary action.
- Let typography and spacing carry hierarchy; avoid decorative labels and repeated all-caps eyebrows.
- Use an editorial serif for the question itself and the existing interface sans-serif for controls and supporting copy.
- Prefer thin rules, margins and precise alignment over rounded containers and repeated shadows.
- Answer choices form one ordered sheet/list; they are not independent floating cards.
- The current question may use a single architectural margin line as the memorable visual device. Do not add competing decoration.
- Keep motion response-driven. Avoid staggered entrance effects and generic hover animation everywhere.
- Pixel-lock selection may use technical-drawing conventions such as crosshair interaction, hatching and compact uppercase region labels because those marks communicate editing geometry.

## Design review checklist

Before merging questionnaire visual changes, ask:

1. Does this look specific to an architecture workflow rather than a reusable SaaS template?
2. Is every border, label, number and divider carrying information?
3. Is the active question still the strongest element on a phone?
4. Can a user complete the step one-handed without hunting for the action?
5. Did the visual change leave questionnaire semantics, skip rules and branching untouched?
