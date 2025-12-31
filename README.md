# Cura Profile Builder

[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![No Dependencies](https://img.shields.io/badge/dependencies-none-green.svg)]()

**Create importable `.curaprofile` files for Cura slicer.**

Build custom quality profiles from presets, previous extractions, or manual settings — then import directly into Cura.

---

## Features

- **Preset Templates** — PLA, PETG, ABS, TPU, ASA × draft/normal/fine/ultra
- **Import from JSON** — Use extractions from [Cura Profile Extractor](https://github.com/ixhlbxi/Cura_Profile_Extractor)
- **Setting Validation** — Validates against Cura's fdmprinter.def.json constraints
- **Auto-Detection** — Finds Cura installation and detects `setting_version`
- **Smart Separation** — Automatically splits global vs per-extruder settings
- **Zero Dependencies** — Python standard library only

---

## Quick Start

### Build from Preset

```bash
# PLA with normal quality for Ender 3 Pro
python cura_profile_builder.py --preset PLA/normal --definition creality_ender3pro

# PETG with fine quality, custom name
python cura_profile_builder.py --preset PETG/fine --definition prusa_mk3s --name "My PETG Fine"
```

### Build from Extraction JSON

First, extract your current settings with [Cura Profile Extractor](https://github.com/ixhlbxi/Cura_Profile_Extractor):

```bash
# Extract current Cura settings to JSON
python cura_profile_extractor.py --cli --machine "My Printer" -o my_settings.json

# Build a new profile from that extraction
python cura_profile_builder.py --from-json my_settings.json --name "Imported Profile"
```

### Import into Cura

1. Open Cura
2. Go to **Preferences → Profiles → Import**
3. Select your `.curaprofile` file
4. Done! Profile appears in your quality dropdown

---

## Available Presets

### Materials

| Preset | Temp | Bed | Speed | Description |
|--------|------|-----|-------|-------------|
| PLA | 200°C | 60°C | 50mm/s | Standard, good all-around |
| PETG | 240°C | 80°C | 40mm/s | Higher temps, less cooling |
| ABS | 240°C | 100°C | 50mm/s | Minimal cooling, enclosure recommended |
| TPU | 230°C | 60°C | 25mm/s | Slow and careful, direct drive recommended |
| ASA | 260°C | 100°C | 50mm/s | Like ABS, better UV resistance |

### Quality Levels

| Preset | Layer Height | Description |
|--------|--------------|-------------|
| draft | 0.28mm | Fast prints, visible layers |
| normal | 0.20mm | Balanced speed and quality |
| fine | 0.12mm | Detailed prints, slower |
| ultra | 0.08mm | Maximum detail, very slow |

Combine them: `--preset PLA/fine`, `--preset PETG/draft`, etc.

---

## CLI Reference

```
usage: cura_profile_builder.py [options]

Build Source (choose one):
  --preset MATERIAL/quality    Build from preset (e.g., PLA/normal)
  --from-json FILE.json        Build from Cura Profile Extractor JSON
  --settings key=val,key=val   Build with manual settings

Required:
  --definition, -d NAME        Machine definition (e.g., creality_ender3pro)
  --name, -n NAME              Profile name (shown in Cura)

Optional:
  --quality-type, -q TYPE      Quality type: draft/normal/fine/ultra (default: normal)
  --output, -o FILE            Output path (default: profile_name.curaprofile)
  --install PATH               Cura installation path (auto-detected)
  --appdata PATH               Cura AppData path (auto-detected)

Info:
  --list-presets               Show available presets
  --help                       Show help
  --version                    Show version
```

---

## Examples

```bash
# List all available presets
python cura_profile_builder.py --list-presets

# Build PLA profile for Creality Ender 3 Pro
python cura_profile_builder.py --preset PLA/normal --definition creality_ender3pro

# Build from extraction with custom output path
python cura_profile_builder.py --from-json extraction.json -o ~/Desktop/my_profile.curaprofile

# Build with manual settings
python cura_profile_builder.py \
  --definition creality_ender3pro \
  --name "Custom Profile" \
  --settings "layer_height=0.16,infill_sparse_density=25,material_print_temperature=210"
```

---

## Finding Your Machine Definition

Machine definitions are in your Cura installation:
```
C:\Program Files\UltiMaker Cura X.X\share\cura\resources\definitions\
```

Common definitions:
- `creality_ender3` / `creality_ender3pro` / `creality_ender3v2`
- `creality_ender5` / `creality_ender5pro`
- `prusa_mk3s` / `prusa_mini`
- `anycubic_i3_mega` / `anycubic_kobra`
- `voron_v0` / `voron_v2`

The builder validates definitions against your Cura installation and will warn if unknown.

---

## Output Format

Generated `.curaprofile` files are ZIP archives containing:

```
My_Profile.curaprofile (ZIP)
├── My_Profile.inst.cfg           # Global settings
└── My_Profile_extruder_0.inst.cfg  # Per-extruder settings
```

Each `.inst.cfg` file follows Cura's INI format:

```ini
[general]
version = 4
name = My Profile
definition = creality_ender3pro

[metadata]
type = quality_changes
quality_type = normal
setting_version = 23

[values]
layer_height = 0.2
material_print_temperature = 200
infill_sparse_density = 20
```

---

## Troubleshooting

### "Could not detect Cura install path"

Set the path manually:
```bash
python cura_profile_builder.py --install "C:\Program Files\UltiMaker Cura 5.11.0" --preset PLA/normal ...
```

Or edit `USER_INSTALL_PATH_OVERRIDE` in the script.

### "Unknown definition"

Check available definitions in your Cura installation:
```
<cura_install>/share/cura/resources/definitions/
```

Use the filename without `.def.json` as your `--definition` value.

### Profile doesn't appear in Cura after import

- Ensure the machine definition matches your configured printer in Cura
- Check Cura's log for import errors: Help → Show Configuration Folder → cura.log

---

## Related Tools

- **[Cura Profile Extractor](https://github.com/ixhlbxi/Cura_Profile_Extractor)** — Extract all Cura settings to searchable JSON
- **Cura Profile Suite** (coming soon) — Combined extract + build workflow

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Changelog

### v1.0.0 (2025-12-30)
- Initial release
- CLI interface with preset and JSON import support
- Setting validation against fdmprinter.def.json
- Auto-detection of Cura paths and setting_version
- Automatic global/extruder setting separation
