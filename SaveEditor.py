import customtkinter as ctk
from tkinter import filedialog
from CTkMessagebox import CTkMessagebox
import struct
import os

# ==========================================
# PART 1: THE CRYPTOGRAPHY ENGINE
# ==========================================
def rc4_crypt(data: bytes) -> bytes:
    key = b"!8\x11`\x17G/S]7$\x0e\x0e\x0f`C/\x0e?\n'UK\x0bOY%8\x0b:D\x17"
    S = list(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + key[i % len(key)]) % 256
        S[i], S[j] = S[j], S[i]
        
    i, j = 0, 0
    out = bytearray()
    for byte in data:
        i = (i + 1) % 256
        j = (j + S[i]) % 256
        S[i], S[j] = S[j], S[i]
        t = (S[i] + S[j]) % 256
        out.append(byte ^ S[t])
        
    return bytes(out)

# ==========================================
# PART 2: THE MEMORY INJECTORS
# ==========================================
def patch_int64_strict(
    data: bytearray, prop_name: bytes, new_val: int, min_offset: int = 8000
) -> bool:
    """Patch a named Int64Property in runtime save data (skip header/schema)."""
    prop_idx = min_offset
    while True:
        prop_idx = data.find(prop_name, prop_idx)
        if prop_idx == -1:
            return False
        type_idx = data.find(b"Int64Property\x00", prop_idx, prop_idx + 45)
        if type_idx != -1:
            val_start = type_idx + 23
            data[val_start : val_start + 8] = struct.pack("<q", new_val)
            return True
        prop_idx += 1


def _bump_gvas_container_sizes(data: bytearray, change_pos: int, delta: int) -> None:
    """
    When serialized property data grows/shrinks, every ancestor StructProperty
    payload size (the u32 after /Script/... type paths) must change by the same delta.
    """
    if delta == 0:
        return
    patched: set[int] = set()
    i = 0
    while i < len(data) - 8:
        if data[i : i + 8] != b"/Script/":
            i += 1
            continue
        end = data.find(b"\x00", i)
        if end == -1 or end >= change_pos:
            i += 1
            continue
        for skip in range(5, 20):
            p = end + skip
            if p + 4 > len(data) or p in patched:
                continue
            if any(data[end + 1 : p]):
                continue
            size = struct.unpack("<I", data[p : p + 4])[0]
            data_start = p + 4
            data_end = data_start + size
            if (
                0 < size < 20_000_000
                and data_start <= change_pos < data_end
            ):
                struct.pack_into("<I", data, p, size + delta)
                patched.add(p)
        i += 1

COLLECTABLE_ENUM_PAIRS = (
    (b"ETtCollectableGameProgressState::Unlocked", b"ETtCollectableGameProgressState::Collected"),
    (b"ETtGameProgressUnlock::Unlocked", b"ETtGameProgressUnlock::Collected"),
)

WAYNE_TECH_CHIPS_PREFIX = b"GameProgress.Definitions.WayneTechChips."
BAT_TOKENS_PREFIX = b"GameProgress.Definitions.BatTokens."


def count_collected_collectables(data: bytes, prefix: bytes) -> int:
    """Count chip/token pickups stored as Collected in GameProgress."""
    count = 0
    idx = 0
    while True:
        pos = data.find(prefix, idx)
        if pos == -1:
            break
        if _entry_is_collected(data[pos : pos + 280]):
            count += 1
        idx = pos + 1
    return count


def _read_enum_length_prefixes(data: bytes, pos: int, enum_len: int) -> tuple[int, int] | None:
    """
    Return the two u32 length fields before an enum FString.
    Layout in save data: [u32 outer_size @ pos-9] [null byte @ pos-5] [u32 fstring_len @ pos-4] [enum chars]
    fstring_len = enum_len + 1 (includes null terminator).
    outer_size  = enum_len + 5 (fstring_len + the 4-byte length field itself).
    """
    if pos < 12:
        return None
    at_9 = struct.unpack("<I", data[pos - 9 : pos - 5])[0]
    at_4 = struct.unpack("<I", data[pos - 4 : pos])[0]
    if at_9 == enum_len + 5 and at_4 == enum_len + 1:
        return (enum_len + 5, enum_len + 1)
    if at_9 == enum_len + 1 and at_4 == enum_len + 5:
        return (enum_len + 1, enum_len + 5)
    return None


def _length_prefixes_for_enum(enum_len: int, layout: tuple[int, int]) -> tuple[int, int]:
    """Map a detected layout to prefix values for a new enum of enum_len."""
    if layout[0] == enum_len + 1:
        return (enum_len + 1, enum_len + 5)
    return (enum_len + 5, enum_len + 1)


def _replace_enum_string(data: bytearray, pos: int, old: bytes, new: bytes) -> bool:
    if data[pos : pos + len(old)] != old:
        return False
    delta = len(new) - len(old)
    if delta not in (0, 1, -1):
        return False
    layout = _read_enum_length_prefixes(data, pos, len(old))
    if layout is None:
        return False
    new_at_10, new_at_5 = _length_prefixes_for_enum(len(new), layout)
    struct.pack_into("<I", data, pos - 9, new_at_10)
    struct.pack_into("<I", data, pos - 4, new_at_5)
    data[pos : pos + len(old)] = new
    if delta:
        _bump_gvas_container_sizes(data, pos, delta)
    return True


def _entry_is_unlocked(chunk: bytes) -> bool:
    return (
        b"ETtCollectableGameProgressState::Unlocked" in chunk
        or b"ETtGameProgressUnlock::Unlocked" in chunk
    )


def _entry_is_collected(chunk: bytes) -> bool:
    return (
        b"SavedEnumNameValue" in chunk
        and (
            b"ETtCollectableGameProgressState::Collected" in chunk
            or b"ETtGameProgressUnlock::Collected" in chunk
        )
        and b"Consumed" not in chunk
    )


def _set_collectable_entry_state(data: bytearray, entry_pos: int, collected: bool) -> bool:
    region = data[entry_pos : entry_pos + 280]
    if b"SavedEnumNameValue" not in region:
        return False
    for unlocked, collected_enum in COLLECTABLE_ENUM_PAIRS:
        ui = region.find(unlocked)
        ci = region.find(collected_enum)
        if collected and ui != -1:
            return _replace_enum_string(data, entry_pos + ui, unlocked, collected_enum)
        if not collected and ci != -1:
            return _replace_enum_string(data, entry_pos + ci, collected_enum, unlocked)
    return False


def _validate_gvas(data: bytes) -> bool:
    if not data.startswith(b"GVAS"):
        return False
    if data.find(b"Int64Property\x00") == -1:
        return False
    return True


def patch_collectable_wallet(
    data: bytearray, prefix: bytes, expected_current: int, target: int
) -> tuple[bool, str]:
    """
    WayneTech chips and Bat tokens are stored as per-pickup GameProgress entries,
    not as a single integer. Adjust how many are marked Collected.
    """
    actual = count_collected_collectables(data, prefix)
    if actual != expected_current:
        return (
            False,
            f"Current amount mismatch: save has {actual:,} collected, you entered {expected_current:,}.",
        )
    if target == actual:
        return True, "No change needed."

    if target > actual:
        need = target - actual
        changed = 0
        positions: list[int] = []
        idx = 0
        while len(positions) < need:
            pos = data.find(prefix, idx)
            if pos == -1:
                return False, f"Only {actual + len(positions):,} total available; cannot reach {target:,}."
            chunk = data[pos : pos + 280]
            if b"SavedEnumNameValue" in chunk and _entry_is_unlocked(chunk):
                positions.append(pos)
            idx = pos + 1
        for pos in reversed(positions):
            if _set_collectable_entry_state(data, pos, True):
                changed += 1
        return True, f"Marked {changed:,} more as collected ({actual:,} -> {target:,})."

    need = actual - target
    changed = 0
    positions: list[int] = []
    idx = 0
    while len(positions) < need:
        pos = data.find(prefix, idx)
        if pos == -1:
            break
        chunk = data[pos : pos + 280]
        if _entry_is_collected(chunk):
            positions.append(pos)
        idx = pos + 1
    for pos in reversed(positions):
        if _set_collectable_entry_state(data, pos, False):
            changed += 1
    if changed != need:
        return False, "Could not remove enough collected entries."
    return True, f"Unmarked {changed:,} pickups ({actual:,} -> {target:,})."

# ==========================================
# PART 3: THE MODERN UI APPLICATION
# ==========================================
class SaveEditorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Batcomputer Terminal: Save Uplink")
        self.root.geometry("520x450") 
        self.root.resizable(False, False)
        
        ctk.set_appearance_mode("dark")
        self.bat_yellow = "#E5A91A"
        self.bat_yellow_hover = "#B38415"
        self.dark_bg = "#1A1A1A"
        
        self.file_path = ""

        # UI Header
        self.header = ctk.CTkLabel(root, text="BATCOMPUTER // SAVE OVERRIDE", font=("Impact", 24), text_color=self.bat_yellow)
        self.header.pack(pady=(15, 5))

        self.btn_select = ctk.CTkButton(
            root, text="LOCATE SAVESLOT_0_TT.SAV", command=self.select_file, 
            fg_color=self.dark_bg, border_color=self.bat_yellow, border_width=2, 
            text_color=self.bat_yellow, hover_color="#2A2A2A", font=("Segoe UI", 12, "bold"), width=300
        )
        self.btn_select.pack(pady=5)
        
        self.lbl_file = ctk.CTkLabel(root, text="No save file selected.", text_color="gray")
        self.lbl_file.pack(pady=(0, 5))

        # Tabbed Interface
        self.tabview = ctk.CTkTabview(
            root, width=470, height=190, 
            segmented_button_selected_color=self.bat_yellow, 
            segmented_button_selected_hover_color=self.bat_yellow_hover,
            segmented_button_unselected_color=self.dark_bg
        )
        self.tabview.pack(expand=True, fill='both', padx=20, pady=5)

        # Tab 1: Primary Overrides (Auto-Detect)
        self.tab_primary = self.tabview.add("Primary Auto-Detect")
        ctk.CTkLabel(self.tab_primary, text="These variables are isolated and will be auto-detected.", font=("Segoe UI", 10, "italic"), text_color="gray").pack(pady=(0, 10))
        self.entry_studs = self.create_standard_row(self.tab_primary, "Studs (Max 9,999,999):")
        self.entry_dinner = self.create_standard_row(self.tab_primary, "Dinner Currency (Max 9,999,999):")

        # Tab 2: Collectables (GameProgress pickup states)
        self.tab_sniper = self.tabview.add("Collectables")
        ctk.CTkLabel(
            self.tab_sniper,
            text="Chips/tokens are stored as collected pickups. Enter your in-game count as Current to verify.",
            font=("Segoe UI", 10, "italic"),
            text_color="gray",
        ).pack(pady=(0, 5))
        self.snipe_chips_curr, self.snipe_chips_new = self.create_sniper_row(self.tab_sniper, "WayneTech Chips:")
        self.snipe_tokens_curr, self.snipe_tokens_new = self.create_sniper_row(self.tab_sniper, "Bat Tokens:")

        # Patch Button
        self.btn_patch = ctk.CTkButton(
            root, text="INJECT PROTOCOL", command=self.run_patch, 
            fg_color=self.bat_yellow, text_color="black", hover_color=self.bat_yellow_hover, 
            font=("Impact", 16), width=250, height=40
        )
        self.btn_patch.pack(pady=15)

    def create_standard_row(self, parent, label_text):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill='x', padx=20, pady=5)
        ctk.CTkLabel(frame, text=label_text, width=220, anchor='w', font=("Segoe UI", 12)).pack(side='left')
        entry = ctk.CTkEntry(frame, width=140, justify="center", border_color="gray", placeholder_text="New Amount")
        entry.pack(side='right')
        return entry

    def create_sniper_row(self, parent, label_text):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill='x', padx=10, pady=5)
        ctk.CTkLabel(frame, text=label_text, width=140, anchor='w', font=("Segoe UI", 12)).pack(side='left')
        entry_target = ctk.CTkEntry(frame, width=100, justify="center", placeholder_text="Target Amount")
        entry_target.pack(side='right', padx=5)
        ctk.CTkLabel(frame, text="->", text_color=self.bat_yellow, font=("Impact", 14)).pack(side='right')
        entry_curr = ctk.CTkEntry(frame, width=100, justify="center", placeholder_text="Current Amount")
        entry_curr.pack(side='right', padx=5)
        return entry_curr, entry_target

    def select_file(self):
        filepath = filedialog.askopenfilename(filetypes=[("Save Files", "*.sav")])
        if filepath:
            self.file_path = filepath
            status = f"Target Acquired: {os.path.basename(filepath)}"
            try:
                with open(filepath, "rb") as f:
                    raw = f.read()
                if raw.startswith(b"GVAS"):
                    plain = raw
                else:
                    plain = rc4_crypt(raw)
                if plain.startswith(b"GVAS"):
                    chips = count_collected_collectables(plain, WAYNE_TECH_CHIPS_PREFIX)
                    tokens = count_collected_collectables(plain, BAT_TOKENS_PREFIX)
                    status += f" | Chips: {chips:,} | Tokens: {tokens:,}"
            except OSError:
                pass
            self.lbl_file.configure(text=status, text_color="#00FF00")

    def validate_single(self, val_str, max_limit, name):
        val_str = val_str.strip().replace(',', '')
        if not val_str: return None
        try: val = int(val_str)
        except: raise ValueError(f"'{name}' must be a number.")
        if val < 0: raise ValueError(f"'{name}' cannot be negative.")
        if val > max_limit: raise ValueError(f"Limit Exceeded for '{name}'!\nMax is {max_limit:,}.")
        return val

    def validate_sniper(self, curr_str, new_str, max_limit, name):
        curr_str, new_str = curr_str.strip().replace(',', ''), new_str.strip().replace(',', '')
        if not curr_str and not new_str: return None, None
        if bool(curr_str) != bool(new_str):
            raise ValueError(f"To snipe '{name}', you must provide BOTH Current and Target amounts.")
        
        try: curr, target = int(curr_str), int(new_str)
        except: raise ValueError(f"Both inputs for '{name}' must be numbers.")
        
        if curr < 0: raise ValueError(f"Current amount for '{name}' cannot be negative.")
        if target > max_limit: raise ValueError(f"Limit Exceeded for '{name}'!\nMax is {max_limit:,}.")
        return curr, target

    def run_patch(self):
        if not self.file_path:
            CTkMessagebox(title="Warning", message="No save file targeted.", icon="warning")
            return

        try:
            # Validate Auto-Detects
            n_studs = self.validate_single(self.entry_studs.get(), 9999999, "Studs")
            n_dinner = self.validate_single(self.entry_dinner.get(), 9999999, "Dinner Currency")
            
            # Validate Snipers
            c_chips, n_chips = self.validate_sniper(self.snipe_chips_curr.get(), self.snipe_chips_new.get(), 9999999, "WayneTech Chips")
            c_tokens, n_tokens = self.validate_sniper(self.snipe_tokens_curr.get(), self.snipe_tokens_new.get(), 999, "Bat Tokens")
        except ValueError as e:
            CTkMessagebox(title="Validation Error", message=str(e), icon="cancel")
            return

        try:
            with open(self.file_path, 'rb') as f: encrypted_data = f.read()
        except Exception as e:
            CTkMessagebox(title="Decryption Error", message=f"Failed to read file:\n{e}", icon="cancel")
            return

        if encrypted_data.startswith(b'GVAS'):
            data = bytearray(encrypted_data)
        else:
            data = bytearray(rc4_crypt(encrypted_data))

        if not data.startswith(b'GVAS'):
            CTkMessagebox(title="Error", message="Decryption failed. Unrecognized structure.", icon="cancel")
            return

        log = []

        # 1. Inject Primary
        if n_studs is not None:
            if patch_int64_strict(data, b"StudsCollected\x00", n_studs):
                log.append(f"- Studs Override: {n_studs:,}")
            else:
                log.append("- Studs Override FAILED: StudsCollected not found.")
        if n_dinner is not None:
            log.append("- Dinner Currency skipped (not stored as a simple Int64 field).")

        # 2. Collectable wallets (GameProgress pickup states)
        if n_chips is not None:
            success, msg = patch_collectable_wallet(data, WAYNE_TECH_CHIPS_PREFIX, c_chips, n_chips)
            if success:
                log.append(f"- WayneTech Chips: {msg}")
            else:
                log.append(f"- WayneTech Chips FAILED: {msg}")

        if n_tokens is not None:
            success, msg = patch_collectable_wallet(data, BAT_TOKENS_PREFIX, c_tokens, n_tokens)
            if success:
                log.append(f"- Bat Tokens: {msg}")
            else:
                log.append(f"- Bat Tokens FAILED: {msg}")

        if not log:
            CTkMessagebox(title="Status", message="No parameters altered.", icon="info")
            return

        if not _validate_gvas(data):
            CTkMessagebox(
                title="Error",
                message="Save structure validation failed. No changes were written.",
                icon="cancel",
            )
            return

        # 3. Repack and Backup
        final_data = bytes(data) if encrypted_data.startswith(b'GVAS') else rc4_crypt(bytes(data))
        backup_path = self.file_path + '.bak'
        if not os.path.exists(backup_path):
            with open(backup_path, 'wb') as f: f.write(encrypted_data)
        with open(self.file_path, 'wb') as f: f.write(final_data)

        CTkMessagebox(title="Injection Successful", message="Payload Injected.\n\n" + "\n".join(log), icon="check")

if __name__ == "__main__":
    root = ctk.CTk()
    app = SaveEditorApp(root)
    root.mainloop()