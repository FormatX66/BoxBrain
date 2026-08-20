# Echo Rally — First Playable Hopper Easter Egg

Echo Rally's first physically playable Hopper state is a permanent Aurum Easter egg.

## Preservation rule

The first-playable implementation is preserved independently of later gameplay polish or rewrites. Future Echo Rally development may improve mechanics, presentation, architecture, or integration, but Aurum must retain a route to launch the original first-playable state.

Frozen source identity:

- canonical source at milestone: `Projects/AurumPC/aurum_echo_native.py`
- Git blob: `af4a5cd4d0abaa250f704f6fee3b3248a56757a8`
- schema: `aurum.echo.native.v2`
- game: `Echo Rally`
- machine milestone: Hopper
- milestone: first physically displayed and locally playable Aurum graphical capability

## Easter-egg behavior

The preserved build should remain discoverable through an intentionally hidden or playful user interaction rather than becoming normal startup behavior. The exact discovery gesture may evolve with the Aurum shell, but the preserved game state must not be silently replaced by a newer Echo implementation.

When launched as the Easter egg, Aurum should identify it as the original first-playable Echo Rally build and use the known-good graphics/input compatibility path available on that generation of the machine.

## Evolution rule

New Echo Rally mechanics belong in descendants. The original is ancestry.

This snapshot is historical capability evidence as well as an Easter egg: it marks the first time Aurum rendered and accepted local input through a real graphical capability on Hopper.
