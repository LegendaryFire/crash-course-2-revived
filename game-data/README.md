Drop the two files here, with these names exactly — they are what an Xbox 360
calls them, so copying them off the drive or out of the live cache keeps them:

| | |
|---|---|
| `92EC7B55A94EF2145A233412B18261DEA2BAE65858` | the game's Xbox Live package, 333 MB, from `Content\0000000000000000\5841124F\000D0000\` |
| `TU_1C424IF_000000K000000.00000000000G5` | the Title Update, 1.4 MB, from the live cache |

`python3 revive.py` reads them from here and writes the game to `../output/`. Nothing
leaves this machine, and git does not commit this folder.
