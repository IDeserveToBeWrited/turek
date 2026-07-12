
# Adds WASD keybind for fly camera for non-numpad users

## Steering
| Control | Keybind | Alternative |
|--|--|--|
| Up | Space | Shift + W* |
| Down | Left Control | Shift + S* |
| Forward | W |
| Backward | S |
| Right | A |
| Left | D |
\* - for some reason it goes diagonally

## Install
Go to `%userprofile%\Documents\Euro Truck Simulator 2\profiles`, enter your profile folder, **make backup** and edit `controls.sii`

Replace

 ```
 config_lines[205]: "mix dbgfwd `keyboard.num8?0`"
 config_lines[206]: "mix dbgback `keyboard.num5?0`"
 config_lines[207]: "mix dbgleft `modifier(no_modifier, keyboard.num4?0)`"
 config_lines[208]: "mix dbgright `modifier(no_modifier, keyboard.num6?0)`"
 config_lines[209]: "mix dbgup `keyboard.num9?0`"
 config_lines[210]: "mix dbgdown `keyboard.num3?0`"
 ```
 With
 ```
 config_lines[205]: "mix dbgfwd `keyboard.num8?0 | keyboard.w?0`"
 config_lines[206]: "mix dbgback `keyboard.num5?0 | keyboard.s?0`"
 config_lines[207]: "mix dbgleft `modifier(no_modifier, keyboard.num4?0) | modifier(no_modifier, keyboard.a?0)`"
 config_lines[208]: "mix dbgright `modifier(no_modifier, keyboard.num6?0) | modifier(no_modifier, keyboard.d?0)`"
 config_lines[209]: "mix dbgup `keyboard.num9?0 | keyboard.space?0 | modifier(shift_only, keyboard.w?0)`"
 config_lines[210]: "mix dbgdown `keyboard.num3?0 | keyboard.lctrl?0 | (keyboard.lshift?0 & keyboard.s?0)`"
```
