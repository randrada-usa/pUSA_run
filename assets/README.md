# Asset handoff

The game currently draws polished placeholder art so that the full game and
camera systems can be tested before the Figma exports arrive.

Export PNG files in sRGB. Use transparent backgrounds for characters,
obstacles, collectibles, icons, and buttons. Keep every frame of one animation
on an identical canvas with the character anchored at the same foot position.

Recommended target canvases:

| Asset | Canvas |
| --- | --- |
| Pipin animation frame | 128 x 128 px |
| Rat animation frame | 128 x 128 px |
| Low obstacle | 128 x 128 px |
| Large single-lane obstacle | up to 192 x 192 px |
| Cat Food and Fish | 64 x 64 px |
| Heart and shield icons | 48 x 48 or 64 x 64 px |
| Seamless environment segment | 1280 x 720 or 1280 x 1440 px |
| Menu background | 1280 x 720 px |
| Standard button | 320 x 80 px |
| Logo | up to 640 x 240 px |

Suggested animation counts:

- Pipin run: 6-8 frames
- Pipin jump: 3-4 frames
- Pipin hurt: 2-3 frames
- Rat run: 4-6 frames
- Rat catch: 4-6 frames

Individual PNG files are preferred for the first handoff. If using sprite
sheets, use a single horizontal row with equally sized frames and no padding
between frames. Do not export mockup backgrounds behind transparent sprites.

