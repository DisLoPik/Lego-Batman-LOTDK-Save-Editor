
#  🦇 Batcomputer Terminal: Save Uplink

###  A Save Editor for *LEGO Batman: Legacy of the Dark Knight*

  

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)

![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows)

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

  

A GUI-based save file editor that lets you modify WayneTech Chips, Bat Tokens, and Studs in your save files. Handles RC4 encryption/decryption automatically — works with both raw encrypted `.sav` files and pre-decrypted `.dec` files.

  

---

  

##  Screenshots

  

> The editor auto-detects your current chip/token counts on file load and reports them in the status bar.

  

---

  

##  Features

  

-  **Auto-Detect** — reads your current Studs count directly from the save

-  **WayneTech Chips** — set how many are marked as collected (per-pickup GameProgress entries)

-  **Bat Tokens** — set how many are marked as collected (per-pickup GameProgress entries)

-  **RC4 transparent** — works on both encrypted `.sav` files and pre-decrypted `.dec` files

-  **Automatic backup** — creates a `.bak` of your original save before writing any changes

-  **Validation** — verifies your entered current count matches the save before patching

  

---

  

##  Requirements

  

-  **Python 3.10 or higher** (uses `tuple[...] | None` type hints)

- The following third-party packages:

  

| Package | Install |

|---|---|

|  `customtkinter`  |  `pip install customtkinter`  |

|  `CTkMessagebox`  |  `pip install CTkMessagebox`  |

  

All other imports (`tkinter`, `struct`, `os`) are part of Python's standard library.

  

Install everything at once:

  

```bash

pip install  customtkinter  CTkMessagebox

```

  

---

  

##  Installation

  

1.  **Clone the repository**

```bash

git clone https://github.com/yourusername/batcomputer-save-editor.git

cd batcomputer-save-editor

```

  

2.  **Install dependencies**

```bash

pip install customtkinter CTkMessagebox

```

  

3.  **Run the editor**

```bash

python SaveEditor.py

```

  

---

  

##  How to Use

  

###  Step 1 — Locate your save file

  

Your save file is typically located at:

  

```

%LOCALAPPDATA%\[GameFolder]\Saved\SaveGames\SaveSlot_0_TT.sav

```

  

> The editor accepts both encrypted `.sav` files and pre-decrypted `.dec` files.

  

###  Step 2 — Load the file

  

Click **LOCATE SAVESLOT_0_TT.SAV** and browse to your save file. Once loaded, the status bar will display:

  

```

Target Acquired: SaveSlot_0_TT.sav | Chips: 12 | Tokens: 9

```

  

This confirms the file was read successfully and shows your current counts.

  

###  Step 3 — Edit your values

  

The editor has two tabs:

  

####  Primary Auto-Detect

| Field | Description |

|---|---|

| Studs | Set your total stud count (max 9,999,999) |

| Dinner Currency | Not editable (not stored as a simple integer in this version) |

  

####  Collectables

Chips and tokens are stored as individual per-pickup entries in the save, not as a single counter. To edit them:

  

1. Enter your **current in-game count** in the left field — this must match what the save actually contains, and is used to verify you loaded the right file

2. Enter your **target count** in the right field

3. The editor will mark or unmark the appropriate number of pickups as collected

  

> ⚠️ You cannot set a target higher than the total number of pickups that exist in the save. The status bar count when you load the file shows how many are currently collected, not the total available.

  

###  Step 4 — Inject

  

Click **INJECT PROTOCOL**. A confirmation dialog will show exactly what was changed. Your original file is automatically backed up as `SaveSlot_0_TT.sav.bak` before anything is written.

  

---

  

##  Troubleshooting

  

**"Current amount mismatch" error**

The count you typed in the *Current Amount* field doesn't match what was found in the save. Re-load the file and use the number shown in the status bar.

  

**Studs Override FAILED**

The `StudsCollected` property wasn't found in the expected location. This can happen if you loaded the wrong save slot or a corrupted file.

  

**Nothing changes after injecting**

Make sure you're loading the save file from the correct path. Some builds of the game may store saves in a different directory.

  

**The app won't start**

Make sure you have Python 3.10+ and both pip packages installed. You can verify with:

```bash

python --version

pip show  customtkinter  CTkMessagebox

```

  

---

  

##  Technical Notes

  

Save files are RC4-encrypted using a fixed key embedded in the engine. The editor decrypts the file in memory, applies patches to the GVAS binary structure, then re-encrypts before writing. If a pre-decrypted `.dec` file is passed in, encryption is skipped automatically.

  

Collectable values (chips and tokens) are not stored as integers — they exist as named `GameProgress` entries with an enum field (`ETtCollectableGameProgressState`) that is either `Unlocked` or `Collected`. The editor scans for entries matching the relevant prefix and flips the enum value for the required number of entries.

  

---

  

##  Disclaimer

  

This tool is a fan project and is not affiliated with or endorsed by TT Games, Warner Bros., or DC Comics. Use at your own risk. Always keep backups of your save files — the editor creates one automatically, but having an extra copy never hurts.
