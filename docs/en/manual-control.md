# Manual direct control

> [Back to index](index.md) · [Project overview](../../README.md)

Tap **直控** in the top bar to enter direct-control mode:

- **Gestures**: outside direct control, double-tap the screen to open the
  mouse/keyboard panel, or swipe up to open the log drawer;
- **Touch**: tap the live screen for left-click, double-tap for double-click, hold and drag to drag, wheel/swipe to scroll;
- **Virtual mouse**: mouse and keyboard are shown together; the touchpad uses
  **relative movement** (finger motion moves the cursor proportionally without
  jumping), supporting tap / double-tap / long-press right-click / drag, plus
  left-click, double-click, right-click and scroll buttons;
- **Virtual keyboard**: alphanumeric keys, Shift/Ctrl/Alt/Win combos, arrows,
  Enter, Backspace, Tab, Esc and Space.

The panel has a collapse/expand button and each section folds independently; a
draggable divider resizes the mouse area, and the dotted handle on the panel's
top edge resizes the whole panel (the keyboard stretches with it), keeping the
screen visible on small phones.

Events are sent as `manual_input` messages over `/ws/control` and applied to the
input backend directly, without the model. If an Agent task is running, the
first manual event requests it to stop, providing interruption and takeover.
